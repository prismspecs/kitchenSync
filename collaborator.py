#!/usr/bin/env python3
"""
kSync Collaborator - Main entry point for the Collaborator role.
Receives time sync from the Leader and adjusts local playback.
Supports Bystander mode for remote provisioning.
"""

import sys
import os
import time
import argparse
import signal
import statistics
import threading
import urllib.request
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from config.manager import ConfigManager
from video import get_video_driver
from video.file_manager import VideoFileManager
from networking.communication import CommandListener, SyncReceiver
from core.system_state import SystemState
from core.logger import log_info, log_error, log_warning, enable_system_logging
from ui.window_manager import hide_mouse_cursor


class CollaboratorPi:
    def __init__(self, config_file=None):
        # Default to ksync.ini if not specified
        config_file = config_file or "ksync.ini"
        self.config = ConfigManager(config_file)
        enable_system_logging(self.config.debug_mode)

        log_info(f"Starting kSync Node '{self.config.device_id}' (Role: {self.config.role_name()})", component="collaborator")

        # Core Components
        self.system_state = SystemState()
        self.video_manager = VideoFileManager(self.config.video_file, self.config.usb_mount_point)

        # Video Driver
        driver_name = self.config.video_driver
        self.video_player = get_video_driver(
            driver_name,
            debug_mode=self.config.debug_mode,
            enable_audio=self.config.enable_audio
        )

        if not self.video_player:
            log_error("Failed to initialize video driver", component="collaborator")
            sys.exit(1)

        # Initialize Protocols (MIDI/OSC)
        self.midi_manager = None
        self.midi_scheduler = None
        self.osc_handler = None

        if self.config.enable_midi:
            from protocols.midi_handler import MidiManager, MidiScheduler
            midi_port = self.config.getint("midi_port", 0)
            self.midi_manager = MidiManager(midi_port)
            self.midi_scheduler = MidiScheduler(self.midi_manager)
            log_info("MIDI: Initialized", component="collaborator")

        if self.config.enable_osc:
            from protocols.osc_handler import OscHandler
            self.osc_handler = OscHandler()
            log_info("OSC: Initialized", component="collaborator")

        # Initialize networking
        self.command_listener = CommandListener()
        self.sync_receiver = SyncReceiver(
            sync_port=self.config.getint("sync_port", 5005),
            sync_callback=self._handle_sync,
        )

        # Sync state
        self.last_sync_at = 0
        self.active_leader_id = None
        self.video_start_time = None
        self.debug_sync_logging = self.config.debug_mode
        self.critical_window_logging = False
        self.debug_deviation_mode = False
        self.deviation_samples = []
        self.max_samples = 3
        self.max_drift = self.config.max_drift
        self.min_drift = self.config.min_drift
        self.kp = self.config.kp
        self.min_rate = self.config.min_rate
        self.max_rate = self.config.max_rate
        self.video_path = None
        self.active_session_key = None
        self.startup_sync_count = 0
        self.FAST_SYNC_THRESHOLD = 10
        self._settle_until = 0

        # Sync Decoupling
        self._latest_sync_state = None
        self._sync_lock = threading.Lock()
        self._sync_thread = None
        self._stop_sync_thread = threading.Event()
        
        self.is_running = False

    def run(self) -> None:
        """Main execution loop"""
        hide_mouse_cursor()
        
        # Register command handlers
        self.command_listener.register_callback(self._handle_command)
        
        # Role-specific startup
        if self.config.is_bystander:
            log_info("Node in BYSTANDER mode. Waiting for remote provisioning.", component="collaborator")
        else:
            log_info("Node in COLLABORATOR mode. Listening for sync...", component="collaborator")
            self.sync_receiver.start_listening()
            
        self.command_listener.start_listening()
        self.is_running = True

        try:
            while self.is_running:
                # Send heartbeat with current role and status
                status = "bystander" if self.config.is_bystander else "ready"
                if self.system_state.is_running:
                    status = "syncing"
                
                try:
                    self.command_listener.send_heartbeat(self.config.device_id, status)
                except Exception as e:
                    log_warning(f"Failed to send heartbeat: {e}", component="collaborator")
                    
                time.sleep(2)
        except KeyboardInterrupt:
            self.cleanup()
        except Exception as e:
            log_error(f"Collaborator main loop crashed: {e}", component="collaborator")
            self.cleanup()

    def _handle_command(self, msg: dict, addr: tuple) -> None:
        """Consolidated command dispatcher"""
        cmd_type = msg.get("type")
        
        # Safety: Ignore playback commands if in bystander mode
        if self.config.is_bystander and cmd_type in ["start", "sync"]:
            return

        if cmd_type == "start":
            self._handle_start_command(msg)
        elif cmd_type == "stop":
            self.stop_playback()
        elif cmd_type == "ping":
            self.command_listener.send_message(
                {"type": "pong", "device_id": self.config.device_id},
                host=addr[0],
            )
        elif cmd_type == "config_request":
            self._handle_config_request(msg, addr)
        elif cmd_type == "config_update":
            self._handle_config_update(msg, addr)
        elif cmd_type == "config_reset":
            self._handle_config_reset(msg, addr)
        elif cmd_type == "file_list_request":
            self._handle_file_list_request(msg, addr)
        elif cmd_type == "file_delete_request":
            self._handle_file_delete_request(msg, addr)
        elif cmd_type == "file_upload_notify":
            self._handle_file_upload_notify(msg, addr)

    def _message_targets_this_device(self, msg: dict) -> bool:
        target_device_id = msg.get("target_device_id")
        return not target_device_id or target_device_id == self.config.device_id

    def _handle_config_request(self, msg: dict, addr: tuple) -> None:
        if not self._message_targets_this_device(msg):
            return
        
        role = self.config.role_name()
        response = {
            "type": "config_state",
            "device_id": self.config.device_id,
            "role": role,
            "config_path": self.config.get_config_path() or "ksync.ini",
            "fields": self.config.get_editable_fields(role),
            "values": self.config.get_editable_values(role),
        }
        self.command_listener.send_message(response, host=addr[0])

    def _handle_config_update(self, msg: dict, addr: tuple) -> None:
        if not self._message_targets_this_device(msg):
            return

        updates = msg.get("updates", {})
        log_info(f"Applying config updates: {updates}", component="collaborator")
        
        # Save to ksync.ini (Universal)
        self.config.clean_and_save_config("ksync.ini", updates, role=self.config.role_name())
        
        response = {
            "type": "config_update_result",
            "device_id": self.config.device_id,
            "status": "ok",
            "requires_restart": True
        }
        self.command_listener.send_message(response, host=addr[0])
        
        # If role changed or we just want a clean slate after config, restart
        time.sleep(1)
        log_info("Restarting node to apply new configuration...", component="collaborator")
        os.execv(sys.executable, [sys.executable, "kitchensync.py"])

    def _handle_config_reset(self, msg: dict, addr: tuple) -> None:
        if not self._message_targets_this_device(msg):
            return
        
        defaults = self.config.get_default_values(self.config.role_name())
        self.config.clean_and_save_config("ksync.ini", defaults, role=self.config.role_name())
        
        response = {"type": "config_update_result", "device_id": self.config.device_id, "status": "ok", "requires_restart": True}
        self.command_listener.send_message(response, host=addr[0])
        
        time.sleep(1)
        os.execv(sys.executable, [sys.executable, "kitchensync.py"])

    def _handle_file_list_request(self, msg: dict, addr: tuple) -> None:
        if not self._message_targets_this_device(msg):
            return
        response = {"type": "file_list_response", "device_id": self.config.device_id, "media": self.video_manager.list_videos()}
        self.command_listener.send_message(response, host=addr[0])

    def _handle_file_delete_request(self, msg: dict, addr: tuple) -> None:
        if not self._message_targets_this_device(msg):
            return
        filename = msg.get("filename")
        if filename:
            self.video_manager.delete_video(filename)
        self._handle_file_list_request(msg, addr)

    def _handle_file_upload_notify(self, msg: dict, addr: tuple) -> None:
        if not self._message_targets_this_device(msg):
            return
        filename = msg.get("filename")
        source_url = msg.get("source_url")
        if not filename or not source_url:
            return

        def download_task():
            try:
                target_path = os.path.join(self.video_manager.get_primary_video_dir(), filename)
                log_info(f"Downloading {filename} from {source_url}", component="collaborator")
                urllib.request.urlretrieve(source_url, target_path)
                log_info(f"Download complete: {filename}", component="collaborator")
                self._handle_file_list_request(msg, addr)
            except Exception as e:
                log_error(f"Download failed: {e}", component="collaborator")

        threading.Thread(target=download_task, daemon=True).start()

    def _handle_sync(self, leader_time: float, received_at: float, leader_id: str = "unknown", sent_at: float = None) -> None:
        if self.active_leader_id is None:
            self.active_leader_id = leader_id
        elif self.active_leader_id != leader_id:
            return
        self.last_sync_at = received_at
        if not self.system_state.is_running:
            return
        with self._sync_lock:
            self._latest_sync_state = (leader_time, received_at, sent_at)

    def _sync_processor_loop(self) -> None:
        while not self._stop_sync_thread.is_set():
            try:
                self._process_sync_tick()
            except Exception as e:
                log_error(f"Sync error: {e}")
            time.sleep(0.05)

    def _process_sync_tick(self) -> None:
        state = None
        with self._sync_lock:
            state = self._latest_sync_state
        if state and self.system_state.is_running:
            leader_time, received_at, sent_at = state
            adjusted_leader_time = leader_time
            if sent_at:
                transport_latency = received_at - float(sent_at)
                if 0.0 <= transport_latency <= 0.25:
                    adjusted_leader_time += transport_latency
            adjusted_leader_time += max(0.0, time.time() - received_at)
            self.system_state.current_time = adjusted_leader_time
            if self.midi_scheduler:
                self.midi_scheduler.process_cues(adjusted_leader_time)
            self._maintain_video_sync(adjusted_leader_time)

    def _maintain_video_sync(self, leader_time: float) -> None:
        if not self.video_player.is_playing or getattr(self.video_player, "is_seeking", False):
            return
        now = time.time()
        if now < self._settle_until and self.startup_sync_count > 0:
            return
        video_pos = self.video_player.get_position()
        if video_pos is None:
            return
        
        duration = self.video_player.get_duration()
        if duration and duration > 0:
            leader_time %= duration
            video_pos %= duration
            
        deviation = video_pos - leader_time
        if duration and duration > 0:
            if deviation > duration/2: deviation -= duration
            elif deviation < -duration/2: deviation += duration

        self.deviation_samples.append(deviation)
        if len(self.deviation_samples) > self.max_samples:
            self.deviation_samples.pop(0)

        if len(self.deviation_samples) >= self.max_samples or self.startup_sync_count < self.FAST_SYNC_THRESHOLD:
            median_dev = deviation if self.startup_sync_count < self.FAST_SYNC_THRESHOLD else statistics.median(self.deviation_samples)
            if self.startup_sync_count < self.FAST_SYNC_THRESHOLD: self.startup_sync_count += 1

            if abs(median_dev) > 2.0:
                self.video_player.seek(leader_time, accurate=False)
                self.deviation_samples.clear()
                self.startup_sync_count = 0
                self._settle_until = now + 2.5
            elif abs(median_dev) > self.max_drift:
                self.video_player.seek(leader_time, accurate=True)
                self.deviation_samples.clear()
                self._settle_until = now + 1.0
            elif abs(median_dev) > self.min_drift:
                rate = max(self.min_rate, min(self.max_rate, 1.0 - (median_dev * self.kp)))
                self.video_player.set_speed(rate)
            else:
                self.video_player.set_speed(1.0)

    def _handle_start_command(self, msg: dict) -> None:
        leader_file = msg.get("video_file")
        leader_id = msg.get("leader_id", "unknown")
        start_time = msg.get("start_time", 0.0)
        
        # Identity session for deduplication
        # If we are already running the SAME session (same leader, file, and base time), ignore.
        session_key = (leader_id, leader_file, start_time)
        if self.system_state.is_running and self.active_session_key == session_key:
            # We are already in this session, do not restart
            return

        configured_file = self.config.video_file
        target_file = configured_file or leader_file
        local_video_path = self.video_manager.find_video_file(target_file=target_file)
        
        if not local_video_path and leader_file:
            local_video_path = self.video_manager.find_video_file(target_file=leader_file)
            
        if not local_video_path:
            log_error(f"Could not find video: {target_file}", component="collaborator")
            return

        if self.system_state.is_running:
            self.stop_playback()

        if self.midi_scheduler:
            self.midi_scheduler.load_schedule(msg.get("schedule", []))

        self.video_path = local_video_path
        if self.video_player.load(self.video_path):
            self.active_session_key = session_key
            self.start_playback()

    def start_playback(self) -> None:
        if self.video_path and self.video_player.play():
            self.system_state.start_session()
            self.startup_sync_count = 0
            self.deviation_samples.clear()
            self._settle_until = time.time() + 1.5
            self._stop_sync_thread.clear()
            self._sync_thread = threading.Thread(target=self._sync_processor_loop, daemon=True)
            self._sync_thread.start()
            if self.midi_scheduler:
                self.midi_scheduler.start_playback(self.system_state.start_time, self.video_player.get_duration())

    def stop_playback(self) -> None:
        self._stop_sync_thread.set()
        if self._sync_thread:
            self._sync_thread.join(timeout=1.0)
            self._sync_thread = None
        self.video_player.stop()
        if self.midi_scheduler:
            self.midi_scheduler.stop_playback()
        self.system_state.stop_session()

    def cleanup(self) -> None:
        self.is_running = False
        self.sync_receiver.stop_listening()
        self.command_listener.stop_listening()
        self.stop_playback()
        self.video_player.cleanup()
        if self.midi_manager: self.midi_manager.cleanup()


def main():
    parser = argparse.ArgumentParser(description="kSync Node")
    parser.add_argument("--config", dest="config_file", help="Path to ksync.ini")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    try:
        node = CollaboratorPi(args.config_file)
        if args.debug: enable_system_logging(True)
        node.run()
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
