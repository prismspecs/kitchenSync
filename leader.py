#!/usr/bin/env python3
"""
kSync Leader - Main entry point for the Leader role.
Coordinates playback, broadcasts time sync, and manages collaborators.
"""

import json
import sys
import os
import socket
import threading
import time
import argparse
import signal
from pathlib import Path
from typing import Any

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from config.manager import ConfigManager
from video import get_video_driver
from video.file_manager import VideoFileManager
from networking.communication import SyncBroadcaster, CommandManager
from core.schedule import Schedule
from core import SystemState, get_ntp_status
from core.logger import log_info, log_error, log_warning, log_file_paths, enable_system_logging
from ui.interface import CommandInterface, StatusDisplay
from ui.window_manager import hide_mouse_cursor
from protocols.midi_handler import MidiManager, MidiScheduler


def _log_startup_crash(exc_type, exc_value, exc_tb):
    """Log startup crashes to file — catches import-time errors before logging init."""
    import traceback
    log_dir = Path(__file__).parent / "logs"
    log_dir.mkdir(exist_ok=True)
    with open(log_dir / "startup_crash.log", "a") as f:
        f.write(f"--- CRASH at {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
        traceback.print_exception(exc_type, exc_value, exc_tb, file=f)
    traceback.print_exception(exc_type, exc_value, exc_tb)


sys.excepthook = _log_startup_crash


class LeaderPi:
    def __init__(self, config_file=None):
        # Load configuration
        self.config = ConfigManager(config_file)
        enable_system_logging(self.config.debug_mode or self.config.enable_system_logging)

        log_info("Starting kSync Leader...", component="leader")

        # Check and log NTP status
        ntp_status = get_ntp_status()
        if ntp_status.get("synced"):
            log_info(f"NTP status: Synchronized (stratum={ntp_status['stratum']}, offset={ntp_status['offset']:.6f}s)", component="leader")
        else:
            err = ntp_status.get("error")
            err_msg = f" ({err})" if err else ""
            log_warning(f"NTP status: Unsynchronized/Not configured{err_msg}", component="leader")

        # Core Components
        self.system_state = SystemState()
        self.video_manager = VideoFileManager(self.config.video_file, self.config.usb_mount_point)
        self.schedule = Schedule(self.config.schedule_file)

        # Video Driver
        self.video_driver_name = "none"
        driver_name = self.config.video_driver
        try:
            self.video_player = get_video_driver(
                driver_name,
                debug_mode=self.config.debug_mode,
                enable_audio=self.config.enable_audio,
                config=self.config
            )
        except Exception as e:
            log_error(f"Exception initializing video driver '{driver_name}': {e}", component="leader")
            self.video_player = None

        if not self.video_player:
            log_warning(f"Failed to initialize primary video driver '{driver_name}'. Falling back to mock driver.", component="leader")
            driver_name = "mock"
            try:
                self.video_player = get_video_driver("mock", debug_mode=self.config.debug_mode, enable_audio=False)
            except Exception as e:
                log_error(f"Failed to load mock video driver fallback: {e}", component="leader")
                sys.exit(1)

        self.video_driver_name = driver_name

        # Initialize Networking
        self.sync_broadcaster = SyncBroadcaster(
            sync_port=self.config.getint("sync_port", 5005),
            tick_interval=self.config.tick_interval,
        )
        self.command_manager = CommandManager()

        # Initialize Protocols (MIDI/OSC)
        self.midi_manager = None
        self.midi_scheduler = None
        if self.config.enable_midi:
            self.midi_manager = MidiManager(use_serial=True)
            self.midi_scheduler = MidiScheduler(self.midi_manager)
            log_info("MIDI: Initialized", component="leader")

        # Find video file
        self.video_path = self.video_manager.find_video_file()
        if self.video_path:
            abs_path = os.path.abspath(self.video_path)
            try:
                load_success = self.video_player.load(self.video_path)
                if not load_success:
                    raise RuntimeError("Driver load returned False")
                log_info(f"Leader Loaded: {abs_path}", component="leader")
                log_info(f"Video file basename (broadcasted): {Path(self.video_path).name}", component="leader")
            except Exception as e:
                log_error(f"Failed to load video '{abs_path}' under '{driver_name}' driver: {e}. Falling back to mock driver.", component="leader")
                try:
                    self.video_player = get_video_driver("mock", debug_mode=self.config.debug_mode, enable_audio=False)
                    self.video_player.load(self.video_path)
                    self.video_driver_name = "mock (fallback from gst)"
                    log_info(f"Leader Loaded (Mock fallback): {abs_path}", component="leader")
                except Exception as me:
                    log_error(f"Failed to load video on mock fallback driver: {me}", component="leader")
        else:
            log_error("No video file found in leader search paths!", component="leader")

        # Register remote control handlers
        self.command_manager.register_handler("start", lambda msg, addr: self.start_system())
        self.command_manager.register_handler("remote_start", lambda msg, addr: self.start_system())
        self.command_manager.register_handler("stop", lambda msg, addr: self.stop_system())
        self.command_manager.register_handler("remote_stop", lambda msg, addr: self.stop_system())
        self.command_manager.register_handler("remote_seek", lambda msg, addr: self.seek_video(str(msg.get("value", 0))))
        self.command_manager.register_handler("remote_set", lambda msg, addr: self.set_sync_param(msg.get("param"), msg.get("value")))
        self.command_manager.register_handler("config_request", lambda msg, addr: self._handle_config_request(msg, addr))
        self.command_manager.register_handler("config_update", lambda msg, addr: self._handle_config_update(msg, addr))
        self.command_manager.register_handler("discover", lambda msg, addr: self._handle_discover(msg, addr))
        self.command_manager.register_handler("device_update", lambda msg, addr: self._handle_device_update(msg, addr))
        self.command_manager.register_handler("log_request", lambda msg, addr: self._handle_log_request(msg, addr))
        self.command_manager.register_handler("file_list_request", lambda msg, addr: self._handle_file_list_request(msg, addr))
        self.command_manager.register_handler("file_delete_request", lambda msg, addr: self._handle_file_delete_request(msg, addr))

        self.command_manager.start_listening()
        self.command_manager.start_latency_probing()

    @staticmethod
    def _ip_is_local(ip: str) -> bool:
        """True if the IP is bound to one of this machine's own interfaces."""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.bind((ip, 0))
            s.close()
            return True
        except OSError:
            return False

    def _send_unicast(self, payload: dict, host: str) -> None:
        """Send a UDP message directly to a specific host (no broadcast)."""
        try:
            self.command_manager._ensure_send_socket()
            data = json.dumps(payload).encode()
            self.command_manager.control_sock.sendto(data, (host, self.command_manager.control_port))
            print(f"[UNICAST] Sent {payload.get('type')} to {host}")
        except Exception as e:
            print(f"[UNICAST] FAILED to send {payload.get('type')} to {host}: {e}")

    def _handle_discover(self, msg: dict, addr: tuple) -> None:
        print(f"[DISCOVER] Received discover from {addr[0]}:{addr[1]}")
        self._refresh_driver_name()
        is_optimized = False
        if self.video_path:
            try:
                is_optimized = self.video_manager.get_metadata(self.video_path).get("is_optimized", False)
            except Exception:
                pass
        response = {
            "type": "leader_announce",
            "device_id": self.config.device_id,
            "status": "leader",
            "video_file": Path(self.video_path).name if self.video_path else "",
            "video_driver": self.video_driver_name,
            "is_optimized": is_optimized,
        }
        self._send_unicast(response, addr[0])

    def _handle_device_update(self, msg: dict, addr: tuple) -> None:
        target = msg.get("target_device_id")
        if target and target != self.config.device_id:
            return
        log_info("Device update requested — git pull && reboot", component="leader")
        print("[UPDATE] Starting device update sequence...")

        def _do_update():
            import subprocess
            repo = os.path.dirname(os.path.abspath(__file__))
            try:
                result = subprocess.run(
                    ["git", "pull"],
                    cwd=repo, capture_output=True, text=True, timeout=30,
                )
                print(f"[UPDATE] git pull: {result.stdout.strip() or result.stderr.strip()}")
            except Exception as e:
                log_warning(f"Update git pull failed: {e}", component="leader")
                print(f"[UPDATE] git pull failed: {e}")

            import time
            time.sleep(2)
            reboot_commands = [
                ["sudo", "-n", "reboot"],
                ["sudo", "-n", "/sbin/reboot"],
                ["sudo", "-n", "/usr/sbin/reboot"],
                ["sudo", "-n", "systemctl", "reboot"],
            ]
            for cmd in reboot_commands:
                result = subprocess.run(
                    cmd, capture_output=True, text=True,
                )
                log_info(f"Device update: {' '.join(cmd)} returned rc={result.returncode} — {result.stderr.strip() or result.stdout.strip()}", component="leader")
                if result.returncode == 0:
                    return
            log_error(f"Device update: all reboot attempts failed — last stderr: {result.stderr.strip()}", component="leader")

        threading.Thread(target=_do_update, daemon=True).start()

    def _handle_log_request(self, msg: dict, addr: tuple) -> None:
        target = msg.get("target_device_id")
        if target and target != self.config.device_id:
            return

        try:
            log_paths = log_file_paths()
            sys_log_path = log_paths.get("system", "logs/kitchensync.log")
            if os.path.exists(sys_log_path):
                with open(sys_log_path, "r", errors="replace") as f:
                    lines = f.readlines()
                    log_content = "".join(lines[-100:])
                    if len(log_content) > 30000:
                        log_content = "... [TRUNCATED] ...\n" + log_content[-30000:]
            else:
                log_content = "No log file found on leader."
        except Exception as exc:
            log_content = f"Error reading logs: {exc}"

        response = {
            "type": "log_response",
            "device_id": self.config.device_id,
            "logs": log_content,
        }
        self._send_unicast(response, addr[0])

    def _refresh_driver_name(self) -> None:
        if self.video_player is None:
            self.video_driver_name = "none"
            return
        driver_type = type(self.video_player).__name__
        if driver_type == "GstDriver":
            sink = getattr(self.video_player, "video_sink_name", None)
            self.video_driver_name = "gst (fakesink)" if sink == "fakesink" else "gst"
        elif driver_type == "MockVideoDriver":
            self.video_driver_name = "mock"
        else:
            self.video_driver_name = driver_type.lower()

    def start_system(self) -> None:
        """Start the synchronized playback system"""
        if self.system_state.is_running:
            log_warning("System is already running", component="leader")
            return

        log_info("Launching kSync system...", component="leader")
        hide_mouse_cursor()

        # Start system state
        self.system_state.start_session()

        # Load schedule
        if self.midi_scheduler:
            self.midi_scheduler.load_schedule(self.schedule.get_cues())

        # Start video playback
        if self.video_path:
            log_info("Starting video playback...", component="video")
            try:
                self.video_player.play()
                self._refresh_driver_name()
                # If we are on a desktop with a display, try to make it fullscreen
                if os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
                    self.video_player.set_fullscreen(True)
            except Exception as e:
                log_error(f"Exception starting video playback: {e}", component="leader")

        # Start networking
        def media_time_provider():
            try:
                base_time = self.video_player.get_position()
                if base_time is None:
                    return None
                # Broadcast raw media position only.
                # Latency compensation is now handled per-device on the
                # collaborator side using EWMA-smoothed one-way transport
                # latency, which is more accurate than a global RTT average.
                return base_time
            except Exception:
                return None

        self.sync_broadcaster.set_time_provider(media_time_provider)
        self.sync_broadcaster.set_duration_provider(self.video_player.get_duration)
        self.sync_broadcaster.leader_id = self.config.device_id
        self.sync_broadcaster.is_wall_clock = "fakesink" in self.video_driver_name or "mock" in self.video_driver_name
        peer_ip = (self.config.get("sync_peer_ip", "") or "").strip()
        if peer_ip and self._ip_is_local(peer_ip):
            log_error(
                f"Sync: sync_peer_ip {peer_ip} is THIS device's own address - collaborators would receive "
                f"no sync at all. Ignoring it and using broadcast. Set it to the COLLABORATOR's IP or remove it.",
                component="leader",
            )
            peer_ip = ""
        if peer_ip:
            log_warning(f"Sync: Using unicast to peer {peer_ip} over Ethernet (WiFi broadcast disabled)", component="leader")
            self.sync_broadcaster.set_unicast_targets([peer_ip], use_broadcast=False)
        self.sync_broadcaster.start_broadcasting(self.system_state.start_time)

        # Start MIDI playback
        video_duration = self.video_player.get_duration()
        if self.midi_scheduler:
            self.midi_scheduler.start_playback(0.0, video_duration)

        # Periodically send start command to collaborators
        def start_broadcast_loop():
            def build_start_command():
                cmd = {
                    "type": "start",
                    "video_file": Path(self.video_path).name if self.video_path else None,
                    "schedule": self.schedule.get_cues(),
                    "start_time": self.system_state.start_time,
                    "leader_id": self.config.device_id,
                    "debug_mode": self.config.debug_mode,
                    # NOTE: sync tuning is per-device config, NOT leader-pushed.
                    # A "sync_params" payload used to be broadcast here but no
                    # collaborator ever read it (removed 2026-07-07).
                }
                # Re-read base_time on every send: it changes whenever this
                # pipeline rebases (gapless-loop setup seek, EOS flush
                # fallback, manual seeks), and a stale value permanently
                # offsets any collaborator that joins with it.
                if getattr(self.config, "sync_mode", "udp") == "netclock" and hasattr(self.video_player, "get_pipeline_base_time"):
                    gst_base_time = self.video_player.get_pipeline_base_time()
                    if gst_base_time:
                        cmd["gst_base_time"] = gst_base_time
                        cmd["netclock_port"] = self.config.getint("netclock_port", 9997)
                return cmd

            # Send immediately on start
            self.command_manager.send_command(build_start_command())

            # Then much slower re-broadcast for late joiners (every 30s instead of 10s)
            while self.system_state.is_running:
                time.sleep(30.0)
                if self.system_state.is_running:
                    # Only broadcast (don't send direct to everyone again to reduce noise)
                    try:
                        self.command_manager._ensure_send_socket()
                        payload = json.dumps(build_start_command())
                        self.command_manager.control_sock.sendto(
                            payload.encode(), (self.command_manager.broadcast_ip, self.command_manager.control_port)
                        )
                    except Exception as e:
                        log_warning(f"Re-broadcast failed: {e}", component="leader")

        threading.Thread(target=start_broadcast_loop, daemon=True).start()

        # MIDI processing loop
        def midi_cue_loop():
            while self.system_state.is_running and self.midi_scheduler:
                current_time = self.video_player.get_position()
                if current_time is not None:
                    self.midi_scheduler.process_cues(current_time)
                time.sleep(0.02)

        if self.midi_scheduler:
            threading.Thread(target=midi_cue_loop, daemon=True).start()

        log_info("System started successfully!", component="leader")

    def stop_system(self) -> None:
        """Stop the synchronized playback system"""
        if not self.system_state.is_running:
            return

        log_info("Stopping kSync system...", component="leader")
        self.video_player.stop()
        self.sync_broadcaster.stop_broadcasting()
        if self.midi_scheduler:
            self.midi_scheduler.stop_playback()
        self.system_state.stop_session()
        self.command_manager.send_command({"type": "stop"})
        log_info("System stopped", component="leader")

    def seek_video(self, time_str: str) -> None:
        """Seek the video to a specific time."""
        if not self.video_player:
            return
        try:
            seconds = float(time_str)
            log_info(f"Seeking video to {seconds} seconds...", component="leader")
            self.video_player.seek(seconds)
            if self.midi_scheduler:
                self.midi_scheduler.reset(seconds)
        except Exception as e:
            log_error(f"An error occurred during seek: {e}", component="leader")

    def cleanup(self) -> None:
        """Clean up resources"""
        if self.system_state.is_running:
            self.stop_system()
        self.video_player.cleanup()
        self.command_manager.stop_listening()
        if self.midi_manager:
            self.midi_manager.cleanup()
        log_info("Cleanup completed", component="leader")

    def set_sync_param(self, param: str, value: Any) -> None:
        """Set a sync parameter live"""
        try:
            if param == "tick_interval":
                val = float(value)
                self.sync_broadcaster.tick_interval = val
                log_info(f"Sync interval set to {val}s", component="leader")
            elif hasattr(self.config, param):
                # ConfigManager handles internal type conversion for getboolean/getfloat
                # But here we are setting it directly on the config object if possible,
                # or just updating the internal config parser.
                self.config.set_param(param, value)
                log_info(f"Parameter {param} set to {value}", component="leader")
        except Exception as e:
            log_error(f"Failed to set parameter {param}: {e}", component="leader")

    def _handle_file_list_request(self, msg: dict, addr: tuple) -> None:
        """Reply with the local media list."""
        if not self._message_targets_this_device(msg):
            return

        response = {
            "type": "file_list_response",
            "device_id": self.config.device_id,
            "media": self.video_manager.list_videos(),
        }
        self._send_unicast(response, addr[0])

    def _handle_file_delete_request(self, msg: dict, addr: tuple) -> None:
        """Delete a local file and report updated list."""
        if not self._message_targets_this_device(msg):
            return

        filename = msg.get("filename")
        if filename:
            self.video_manager.delete_video(filename)

        # Always reply with updated list
        self._handle_file_list_request(msg, addr)

    def _message_targets_this_device(self, msg: dict) -> bool:
        target_device_id = msg.get("target_device_id")
        return not target_device_id or target_device_id == self.config.device_id

    def _handle_config_request(self, msg: dict, addr: tuple) -> None:
        """Reply with current configuration."""
        if not self._message_targets_this_device(msg):
            return
        response = {
            "type": "config_state",
            "device_id": self.config.device_id,
            "role": "leader",
            "fields": self.config.get_editable_fields("leader"),
            "values": self.config.get_editable_values("leader"),
            "config_path": self.config.get_config_path() or "ksync.ini"
        }
        self.command_manager.send_command(response, target_pi=None)

    def _handle_config_update(self, msg: dict, addr: tuple) -> None:
        """Handle a configuration update from the remote controller."""
        # Config updates are broadcast (direct send + broadcast fallback), so
        # an update addressed to a collaborator also arrives here. Applying it
        # once overwrote this leader's ksync.ini with the collaborator's
        # entire config (role, device_id and all), demoting it to a second
        # collaborator on the next restart.
        if not self._message_targets_this_device(msg):
            return
        updates = msg.get("updates", {})
        log_info(f"Applying leader config updates: {updates}", component="leader")
        
        self.config.clean_and_save_config("ksync.ini", updates, role="leader")
        
        restart_keys = {"role", "sync_peer_ip"}
        response = {
            "type": "config_update_result",
            "device_id": self.config.device_id,
            "status": "ok",
            "requires_restart": bool(restart_keys & updates.keys())
        }
        self.command_manager.send_command(response, target_pi=None)
        
        current_video = Path(self.video_path).name if self.video_path else ""
        video_changed = bool(updates.get("video_file")) and updates["video_file"] != current_video
        if ("role" in updates and updates["role"] != "leader") or video_changed:
            reason = "Role change" if "role" in updates and updates["role"] != "leader" else "Video change"
            log_info(f"{reason} detected. Restarting...", component="leader")
            time.sleep(1)
            os.execv(sys.executable, [sys.executable, "kitchensync.py"])


def main():
    parser = argparse.ArgumentParser(description="kSync Leader Node")
    parser.add_argument("--config", dest="config_file", help="Path to config file")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    parser.add_argument("--auto", action="store_true", help="Start playback automatically")
    args = parser.parse_args()

    def signal_handler(sig, frame):
        if "leader_instance" in locals():
            leader_instance.cleanup()
        sys.exit(0)

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    try:
        leader_instance = LeaderPi(args.config_file)
        if args.debug:
            enable_system_logging(True)

        if args.auto:
            try:
                leader_instance.start_system()
            except Exception as e:
                log_error(f"Auto-start playback failed: {e}. Keeping leader process alive for remote Web UI command control.", component="leader")
            while True:
                time.sleep(1)
        else:
            interface = CommandInterface("kSync Leader")
            interface.register_command("start", leader_instance.start_system, "Start synchronized playback")
            interface.register_command("stop", leader_instance.stop_system, "Stop synchronized playback")
            interface.register_command("status", lambda: StatusDisplay.show_leader_status(
                leader_instance.system_state, leader_instance.command_manager.get_collaborators(), 0
            ), "Show system status")
            interface.register_command("set", leader_instance.set_sync_param, "Set sync parameter")
            interface.run()
        leader_instance.cleanup()
    except Exception as e:
        log_error(f"Fatal leader startup error: {e}", component="leader")
        time.sleep(30)
        sys.exit(1)


if __name__ == "__main__":
    main()
