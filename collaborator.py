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
import statistics
import threading
import urllib.request
from pathlib import Path
from typing import Optional


# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from config.manager import ConfigManager
from video import get_video_driver
from video.file_manager import VideoFileManager
from networking.communication import CommandListener, SyncReceiver
from core import SystemState, get_ntp_status
from core.logger import log_info, log_error, log_warning, enable_system_logging
from core.node_common import (
    install_startup_crash_logger,
    message_targets_this_device,
    start_device_update,
    read_recent_log,
)
from ui.window_manager import hide_mouse_cursor


install_startup_crash_logger(Path(__file__).parent)


class CollaboratorPi:
    def __init__(self, config_file=None):
        # Default to ksync.ini if not specified
        config_file = config_file or "ksync.ini"
        self.config = ConfigManager(config_file)
        enable_system_logging(self.config.debug_mode or self.config.enable_system_logging)

        log_info(f"Starting kSync Node '{self.config.device_id}' (Role: {self.config.role_name()})", component="collaborator")

        # Check and log NTP status
        ntp_status = get_ntp_status()
        if ntp_status.get("synced"):
            log_info(f"NTP status: Synchronized (stratum={ntp_status['stratum']}, offset={ntp_status['offset']:.6f}s)", component="collaborator")
        else:
            err = ntp_status.get("error")
            err_msg = f" ({err})" if err else ""
            log_warning(f"NTP status: Unsynchronized/Not configured{err_msg}", component="collaborator")

        # Core Components
        self.system_state = SystemState()
        self.video_manager = VideoFileManager(self.config.video_file, self.config.usb_mount_point)

        # Video Driver
        driver_name = self.config.video_driver
        self.video_player = get_video_driver(
            driver_name,
            debug_mode=self.config.debug_mode,
            enable_audio=self.config.enable_audio,
            config=self.config
        )

        if not self.video_player:
            log_error("Failed to initialize video driver", component="collaborator")
            sys.exit(1)

        self.video_driver_name = driver_name

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
        self._sync_source = "media"
        self._play_start_wall = None
        self.video_start_time = None
        self.debug_sync_logging = self.config.debug_mode
        self.critical_window_logging = False
        self.debug_deviation_mode = False
        self.deviation_samples = []
        self.max_samples = self.config.max_samples
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
        self.hard_seek_count = 0
        self._smoothed_latency = None  # EWMA-smoothed per-device transport latency
        self._current_deviation = 0.0
        self._current_playback_rate = 1.0
        self._netclock_fallback_warned = False
        self._last_hard_seek_at = 0.0

        # Sync Decoupling
        self._latest_sync_state = None
        self._sync_lock = threading.Lock()
        self._sync_thread = None
        self._stop_sync_thread = threading.Event()
        
        self.is_running = False

        # Deviation Logging
        self.enable_deviation_log = getattr(self.config, "enable_deviation_log", False)
        if self.enable_deviation_log:
            self._init_deviation_log()

    def _init_deviation_log(self) -> None:
        log_dir = Path(__file__).parent / "logs"
        log_dir.mkdir(exist_ok=True)
        self.deviation_log_path = log_dir / "sync_deviation.csv"
        if not self.deviation_log_path.exists() or self.deviation_log_path.stat().st_size == 0:
            try:
                with open(self.deviation_log_path, "w") as f:
                    f.write("timestamp,leader_time,video_pos,deviation,rate,hard_seeks\n")
            except Exception as e:
                log_error(f"Failed to initialize deviation CSV: {e}", component="collaborator")

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
                
                # Retrieve currently playing video and optimized status
                video_file = ""
                is_optimized = False
                current_path = getattr(self, "video_path", None)
                if current_path:
                    video_file = os.path.basename(current_path)
                    meta = self.video_manager.get_metadata(current_path)
                    is_optimized = meta.get("is_optimized", False)
                elif self.config.video_file:
                    video_file = os.path.basename(self.config.video_file)
                    resolved = self.video_manager.find_video_file(self.config.video_file)
                    if resolved:
                        meta = self.video_manager.get_metadata(resolved)
                        is_optimized = meta.get("is_optimized", False)
                
                try:
                    self.command_listener.send_heartbeat(
                        self.config.device_id,
                        status,
                        hard_seeks=self.hard_seek_count,
                        video_file=video_file,
                        is_optimized=is_optimized,
                        video_driver=getattr(self, "video_driver_name", ""),
                        sync_deviation=self._current_deviation,
                        playback_rate=self._current_playback_rate,
                    )
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
            self._handle_start_command(msg, addr)
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
        elif cmd_type == "reset_seeks":
            self.hard_seek_count = 0
            log_info("Sync: Hard seek counter reset manually via command.", component="collaborator")
        elif cmd_type == "log_request":
            self._handle_log_request(msg, addr)
        elif cmd_type == "latency_update":
            self._handle_latency_update(msg)
        elif cmd_type == "device_update":
            self._handle_device_update(msg)

    def _handle_latency_update(self, msg: dict) -> None:
        latency = msg.get("latency", 0.0)
        if latency > 0.0:
            if self._smoothed_latency is None:
                self._smoothed_latency = latency
            else:
                alpha = 0.3
                self._smoothed_latency = alpha * latency + (1 - alpha) * self._smoothed_latency
            if self.config.debug_mode:
                log_info(f"Sync: Updated smoothed transport latency to {self._smoothed_latency*1000:.1f}ms", component="collaborator")

    def _handle_device_update(self, msg: dict) -> None:
        if not self._message_targets_this_device(msg):
            return
        start_device_update(component="collaborator")

    def _message_targets_this_device(self, msg: dict) -> bool:
        return message_targets_this_device(msg, self.config.device_id)

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

    def _handle_log_request(self, msg: dict, addr: tuple) -> None:
        if not self._message_targets_this_device(msg):
            return

        response = {
            "type": "log_response",
            "device_id": self.config.device_id,
            "logs": read_recent_log(missing_note="No log file found on collaborator."),
        }
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
            import shutil
            import subprocess
            import urllib.error
            try:
                sync_mode = self.config.remote_sync_mode
                target_path = os.path.join(self.video_manager.get_primary_video_dir(), filename)
                rsync_success = False

                if sync_mode == "rsync":
                    rsync_bin = shutil.which("rsync")
                    if rsync_bin:
                        leader_ip = addr[0]
                        log_info(f"Rsync: Attempting rsync sync for {filename} from {leader_ip}", component="collaborator")
                        try:
                            # Try to sync from leader's media folder (assuming standard kSync installation structure)
                            cmd = [rsync_bin, "-avz", "--timeout=10", f"{leader_ip}:workbench/kitchenSync/media/{filename}", target_path]
                            subprocess.run(cmd, check=True)
                            rsync_success = True
                            log_info(f"Rsync complete: {filename}", component="collaborator")
                            self.video_manager.trigger_background_scan(force=True)
                            self._handle_file_list_request(msg, addr)
                        except Exception as re:
                            log_warning(f"Rsync failed ({re}). Falling back to HTTP resume downloader", component="collaborator")
                    else:
                        log_warning("Rsync binary not found. Falling back to HTTP resume downloader", component="collaborator")

                if not rsync_success:
                    # Robust HTTP Resume Downloader with chunked streams
                    req = urllib.request.Request(source_url)
                    existing_size = 0
                    if os.path.exists(target_path):
                        existing_size = os.path.getsize(target_path)
                    
                    if existing_size > 0:
                        req.add_header("Range", f"bytes={existing_size}-")
                        log_info(f"HTTP: Requesting Range bytes={existing_size}- to resume download of {filename}", component="collaborator")
                    else:
                        log_info(f"HTTP: Downloading {filename} from scratch", component="collaborator")
                    
                    try:
                        with urllib.request.urlopen(req) as response:
                            status = response.status if hasattr(response, "status") else response.getcode()
                            
                            if status == 206:
                                log_info(f"HTTP: Resuming download from byte {existing_size}", component="collaborator")
                                mode = "ab"
                            elif status == 416:
                                log_info(f"HTTP: File already fully downloaded or identical.", component="collaborator")
                                self.video_manager.trigger_background_scan(force=True)
                                self._handle_file_list_request(msg, addr)
                                return
                            else:
                                log_info(f"HTTP: Starting fresh download", component="collaborator")
                                mode = "wb"
                                
                            with open(target_path, mode) as f:
                                block_size = 1024 * 64
                                while True:
                                    buffer = response.read(block_size)
                                    if not buffer:
                                        break
                                    f.write(buffer)
                                    
                        log_info(f"Download complete: {filename}", component="collaborator")
                        self.video_manager.trigger_background_scan(force=True)
                        self._handle_file_list_request(msg, addr)
                    except urllib.error.HTTPError as he:
                        if he.code == 416:
                            log_info(f"HTTP: File already fully downloaded.", component="collaborator")
                            self.video_manager.trigger_background_scan(force=True)
                            self._handle_file_list_request(msg, addr)
                        else:
                            raise he
            except Exception as e:
                log_error(f"Download failed: {e}", component="collaborator")

        threading.Thread(target=download_task, daemon=True).start()

    def _handle_sync(self, leader_time: float, received_at: float, leader_id: str = "unknown", sent_at: float = None, source: str = "media", position_read_time: float = None, leader_ip: str = None) -> None:
        if self.active_leader_id is None:
            self.active_leader_id = leader_id
        elif self.active_leader_id != leader_id:
            return
        self.last_sync_at = received_at
        self._sync_source = source
        if leader_ip:
            self.discovered_leader_ip = leader_ip
        if not self.system_state.is_running:
            return
        with self._sync_lock:
            self._latest_sync_state = (leader_time, received_at, sent_at, source, position_read_time)

    def _sync_processor_loop(self) -> None:
        while not self._stop_sync_thread.is_set():
            try:
                self._process_sync_tick()
            except Exception as e:
                log_error(f"Sync error: {e}")
            time.sleep(0.01)

    def _process_sync_tick(self) -> None:
        state = None
        with self._sync_lock:
            state = self._latest_sync_state
        if state and self.system_state.is_running:
            if len(state) == 5:
                leader_time, received_at, sent_at, source, position_read_time = state
                # Compensate for sender-side processing lag: time between
                # position read and actual packet transmission.
                if sent_at and position_read_time:
                    adjusted_leader_time = leader_time + max(0.0, sent_at - position_read_time)
                else:
                    adjusted_leader_time = leader_time
            elif len(state) == 4:
                leader_time, received_at, sent_at, source = state
                adjusted_leader_time = leader_time
            else:
                leader_time, received_at, sent_at = state
                source = "media"
                adjusted_leader_time = leader_time
            enable_compensation = getattr(self.config, "enable_latency_compensation", False)
            if enable_compensation and self._smoothed_latency is not None:
                adjusted_leader_time += self._smoothed_latency
            # Account for time elapsed since packet arrived (processing lag)
            adjusted_leader_time += max(0.0, time.time() - received_at)
            self.system_state.current_time = adjusted_leader_time
            if self.midi_scheduler:
                self.midi_scheduler.process_cues(adjusted_leader_time)
            # Runs in BOTH sync modes: in netclock mode it measures/logs
            # deviation and acts only as a coarse divergence watchdog.
            self._maintain_video_sync(adjusted_leader_time, source=source)

    def _maintain_video_sync(self, leader_time: float, source: str = "media") -> None:
        if not self.video_player.is_playing or getattr(self.video_player, "is_seeking", False):
            return
        now = time.time()
        if now < self._settle_until:
            return
        # Static per-device offset (seconds): positive delays this device
        # relative to the leader. Dials out display-chain latency differences
        # between screens - the residual offset clock sync cannot see.
        video_offset = getattr(self.config, "video_offset", 0.0)
        if video_offset:
            leader_time = leader_time - video_offset
        # Use wall-clock position when leader sends wall-based time (mock driver fallback)
        # to avoid comparing wall-based time against hardware-decoded position (which has
        # a pipeline delay). When the leader uses media position, use get_position().
        if source == "wall" and hasattr(self, "_play_start_wall") and self._play_start_wall:
            video_pos = now - self._play_start_wall
        else:
            video_pos = self.video_player.get_position()
        if video_pos is None:
            return
        
        duration = self.video_player.get_duration()
        if duration and duration > 0:
            leader_time %= duration
            video_pos %= duration
            
        deviation = video_pos - leader_time
        self._current_deviation = deviation
        if duration and duration > 0:
            if deviation > duration/2: deviation -= duration
            elif deviation < -duration/2: deviation += duration

        # Detect if we are near the loop boundary (within 3.0 seconds of the seam).
        # Near boundaries, GStreamer non-flushing loop offsets can transiently 
        # diverge, and flushing seeks are extremely expensive. We suppress standard
        # seeks here and let the P-controller seamlessly adjust speed, unless there
        # is a massive out-of-sync situation (> 5.0s).
        is_near_loop = False
        # Suppress loop boundary seek-suppression during the initial startup sync phase 
        # so that the collaborator can snap to the leader's position immediately.
        if self.startup_sync_count >= self.FAST_SYNC_THRESHOLD:
            if duration and duration > 3.0:
                if video_pos < 3.0 or video_pos > (duration - 3.0):
                    is_near_loop = True

        self.deviation_samples.append(deviation)
        if len(self.deviation_samples) > self.max_samples:
            self.deviation_samples.pop(0)

        if len(self.deviation_samples) >= self.max_samples or self.startup_sync_count < self.FAST_SYNC_THRESHOLD:
            median_dev = deviation if self.startup_sync_count < self.FAST_SYNC_THRESHOLD else statistics.median(self.deviation_samples)
            if self.startup_sync_count < self.FAST_SYNC_THRESHOLD: self.startup_sync_count += 1

            if getattr(self.config, "sync_mode", "udp") == "netclock":
                if getattr(self.video_player, "_net_clock", None) is not None:
                    self._netclock_watchdog(median_dev, leader_time, now)
                    self._log_deviation(now, leader_time, video_pos, deviation)
                    return
                # netclock configured but never established (leader in udp
                # mode, port blocked, ...) - the UDP controller below is the
                # only thing that can correct playback, so fall through.
                if not self._netclock_fallback_warned:
                    self._netclock_fallback_warned = True
                    log_warning(
                        "Sync: netclock configured but no net clock established "
                        "(is the leader also in netclock mode?). Falling back to UDP rate control.",
                        component="collaborator",
                    )

            # Seek overrides for loop boundaries
            allow_hard_seek = abs(median_dev) > 5.0 if is_near_loop else abs(median_dev) > 2.0
            allow_accurate_seek = False if is_near_loop else abs(median_dev) >= self.max_drift

            if allow_hard_seek:
                self.hard_seek_count += 1
                self._current_playback_rate = 1.0
                # Fast KEY_UNIT seeks snap to the nearest keyframe. On
                # long-GOP files that can be the START of the file, so the
                # seek never converges and the collaborator hovers at 0:00
                # until the leader loops around. If the previous hard seek
                # was recent (didn't converge), escalate to frame-accurate.
                accurate = (now - self._last_hard_seek_at) < 15.0
                self._last_hard_seek_at = now
                log_info(f"Sync: Initiating hard seek to {leader_time:.3f}s (dev={median_dev:.3f}s, near_loop={is_near_loop}, accurate={accurate}) [Total hard seeks: {self.hard_seek_count}]", component="collaborator")
                self.video_player.seek(leader_time, accurate=accurate)
                self.deviation_samples.clear()
                self.startup_sync_count = 0
                self._settle_until = now + 2.5
            elif allow_accurate_seek:
                self._current_playback_rate = 1.0
                log_info(f"Sync: Initiating accurate seek to {leader_time:.3f}s (dev={median_dev:.3f}s)", component="collaborator")
                self.video_player.seek(leader_time, accurate=True)
                self.deviation_samples.clear()
                self._settle_until = now + 1.0
            elif abs(median_dev) > self.min_drift:
                rate = max(self.min_rate, min(self.max_rate, 1.0 - (median_dev * self.kp)))
                self._current_playback_rate = rate
                self.video_player.set_speed(rate)
            else:
                self._current_playback_rate = 1.0
                self.video_player.set_speed(1.0)

            self._log_deviation(now, leader_time, video_pos, deviation)

    def _netclock_watchdog(self, median_dev: float, leader_time: float, now: float) -> None:
        """Coarse divergence guard while GStreamer's network clock drives playback.

        The net clock keeps rate perfectly matched, so no rate control or fine
        seeking here — only a realign when playback has grossly diverged
        (leader seek, EOS flush fallback, or a failed clock sync at startup).
        """
        self._current_playback_rate = 1.0
        guard = self.config.getfloat("netclock_max_drift", 0.5)
        if abs(median_dev) <= guard:
            return
        if not hasattr(self.video_player, "netclock_realign"):
            return
        if self.video_player.netclock_realign(leader_time):
            self.hard_seek_count += 1
            log_info(
                f"Sync: NetClock divergence {median_dev:.3f}s exceeded {guard}s - realigned to leader "
                f"[Total realigns: {self.hard_seek_count}]",
                component="collaborator",
            )
            self.deviation_samples.clear()
            self._settle_until = now + 2.5
        else:
            # Realign rejected (pipeline not ready / clock gone) - back off
            # instead of retrying every tick. A failed attempt once spun
            # 14,000 times, inflating the hard-seek counter uselessly.
            log_warning(f"Sync: NetClock realign failed (dev={median_dev:.3f}s); backing off 2.5s", component="collaborator")
            self._settle_until = now + 2.5

    def _log_deviation(self, now: float, leader_time: float, video_pos: float, deviation: float) -> None:
        if not getattr(self, "enable_deviation_log", False):
            return
        try:
            with open(self.deviation_log_path, "a") as f:
                f.write(f"{now:.6f},{leader_time:.6f},{video_pos:.6f},{deviation:.6f},{self._current_playback_rate:.4f},{self.hard_seek_count}\n")
        except Exception:
            pass

    def _handle_start_command(self, msg: dict, addr: Optional[tuple] = None) -> None:
        leader_file = msg.get("video_file")
        leader_id = msg.get("leader_id", "unknown")
        start_time = msg.get("start_time", 0.0)
        
        # Discover leader IP from command address
        if addr:
            self.discovered_leader_ip = addr[0]
            
        configured_file = self.config.video_file
        target_file = configured_file or leader_file
        
        use_cache = getattr(self.config, "enable_caching", False)
        local_video_path = self.video_manager.find_video_file(target_file=target_file, use_cache=use_cache)
        if not local_video_path and leader_file:
            local_video_path = self.video_manager.find_video_file(target_file=leader_file, use_cache=use_cache)
            
        # Identity session for deduplication
        # If we are already running the SAME session (same leader, file, and base time), ignore.
        session_key = (leader_id, target_file, start_time)
        if self.system_state.is_running:
            if getattr(self, "active_session_key", None) == session_key:
                return
            # Legacy fallback: if message has no identity, check if we are already playing the resolved file
            if leader_id == "unknown" and getattr(self, "video_path", None) == local_video_path:
                return
            
        if not local_video_path:
            log_error(f"Could not find video: {target_file}", component="collaborator")
            return

        if self.system_state.is_running:
            self.stop_playback()

        if getattr(self, "midi_scheduler", None):
            self.midi_scheduler.load_schedule(msg.get("schedule", []))

        self.video_path = local_video_path
        if self.video_player.load(self.video_path):
            self.active_session_key = session_key
            
            # Phase 3 GstNetClientClock integration
            if getattr(self.config, "sync_mode", "udp") == "netclock":
                leader_ip = getattr(self, "discovered_leader_ip", None)
                if not leader_ip and addr:
                    leader_ip = addr[0]
                    
                gst_base_time = msg.get("gst_base_time")
                netclock_port = msg.get("netclock_port", 9997)
                
                if leader_ip and gst_base_time is not None:
                    if hasattr(self.video_player, "use_network_clock"):
                        self.video_player.use_network_clock(leader_ip, gst_base_time, netclock_port)
                else:
                    log_warning(f"Sync: Cannot use NetClock yet (ip={leader_ip}, base_time={gst_base_time})", component="collaborator")
            
            self.start_playback()

    def start_playback(self) -> None:
        if self.video_path and self.video_player.play():
            self._play_start_wall = time.time()
            self.system_state.start_session()
            self.hard_seek_count = 0
            self.startup_sync_count = 0
            self.deviation_samples.clear()
            self._settle_until = time.time() + 1.5
            self._netclock_fallback_warned = False
            self._last_hard_seek_at = 0.0
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
        self._play_start_wall = None
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
        if args.debug:
            enable_system_logging(True)
            node.config.debug_mode = True
        node.run()
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
