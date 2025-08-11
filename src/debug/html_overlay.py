#!/usr/bin/env python3
"""
HTML-based debug overlay for KitchenSync
Opens a browser window with live-updating debug information
"""

import os
import time
import threading
import webbrowser
from pathlib import Path
from typing import Optional, Dict, Any
from src.core.logger import log_info, log_error, log_warning
from src.debug.template_engine import DebugTemplateManager


class HTMLDebugOverlay:
    """HTML-based debug overlay that opens in a browser window"""

    def __init__(self, pi_id: str, video_player=None):
        self.pi_id = pi_id
        self.video_player = video_player
        self.running = True
        self.state_lock = threading.Lock()

        # Initialize template system
        template_dir = Path(__file__).parent / "templates"
        self.template_manager = DebugTemplateManager(str(template_dir))
        self.html_file = f"/tmp/kitchensync_debug_{pi_id}/index.html"

        # Initialize state
        self.state = {
            "video_file": "No video",
            "current_time": 0.0,
            "total_time": 0.0,
            "session_time": 0.0,
            "video_position": None,

            "midi_recent": [],
            "midi_upcoming": [],
            "is_leader": False,
            "video_loop_count": 0,
            "midi_loop_count": 0,
            "looping_enabled": True,
        }

        # Track Firefox state
        self.firefox_opened = False

        # Create initial HTML file using templates
        self._create_html_file()

        # Start update thread
        self.update_thread = threading.Thread(target=self._update_loop, daemon=True)
        self.update_thread.start()

    def _create_html_file(self):
        """Create the initial HTML file using templates"""
        try:
            # Get system info for initial render
            system_info = self._get_system_info()

            # Render template
            self.html_file = self.template_manager.render_debug_overlay(
                self.pi_id, system_info
            )

            if not self.html_file:
                raise Exception("Template rendering failed")

            log_info(f"HTML debug file created: {self.html_file}", component="overlay")

        except Exception as e:
            log_error(
                f"Failed to create HTML file using templates: {e}", component="overlay"
            )
            # Fallback to a simple error page
            self._create_fallback_html()

    def _create_fallback_html(self):
        """Create a simple fallback HTML file if template system fails"""
        try:
            # Ensure directory exists
            html_dir = Path(self.html_file).parent
            html_dir.mkdir(parents=True, exist_ok=True)

            fallback_html = f"""<!DOCTYPE html>
<html>
<head>
    <title>KitchenSync Debug - {self.pi_id} (Fallback)</title>
    <meta charset="utf-8">
    <style>
        body {{ font-family: monospace; background: #1a1a2e; color: #fff; margin: 20px; }}
        .error {{ color: #ff6b6b; background: #2d1b1b; padding: 15px; border-radius: 5px; }}
    </style>
</head>
<body>
    <h1>KitchenSync Debug - {self.pi_id}</h1>
    <div class="error">
        <h2>Template System Error</h2>
        <p>The template system failed to load. Using fallback display.</p>
        <p>Please check the template files in src/debug/templates/</p>
    </div>
    <script>
        setTimeout(function() {{ location.reload(); }}, 5000);
    </script>
</body>
</html>"""

            with open(self.html_file, "w") as f:
                f.write(fallback_html)

            log_warning(
                f"Created fallback HTML file: {self.html_file}", component="overlay"
            )

        except Exception as e:
            log_error(f"Failed to create fallback HTML: {e}", component="overlay")

    def _format_midi_event(self, event):
        """Format MIDI event for display"""
        if not event:
            return "None"

        event_type = event.get("type", "unknown")
        time_val = event.get("time", 0)

        if event_type == "note_on":
            note = event.get("note", 0)
            channel = event.get("channel", 1)
            velocity = event.get("velocity", 127)
            return f"{time_val:.1f}s: Note ON Ch{channel} N{note} V{velocity}"
        elif event_type == "note_off":
            note = event.get("note", 0)
            channel = event.get("channel", 1)
            return f"{time_val:.1f}s: Note OFF Ch{channel} N{note}"
        elif event_type == "control_change":
            control = event.get("control", 0)
            value = event.get("value", 0)
            channel = event.get("channel", 1)
            return f"{time_val:.1f}s: CC Ch{channel} C{control} V{value}"
        else:
            return f"{time_val:.1f}s: {event_type}"

    def update_state(self, **kwargs):
        """Update the debug state"""
        with self.state_lock:
            self.state.update(kwargs)

    def _update_loop(self):
        """Update the HTML file with current state"""
        while self.running:
            try:
                self._update_html_file()
                time.sleep(2)  # Update every 2 seconds
            except Exception as e:
                log_error(f"HTML update error: {e}", component="overlay")
                time.sleep(5)

    def _update_html_file(self):
        """Update the HTML file with current state"""
        try:
            with self.state_lock:
                state = self.state.copy()

            # Read the current HTML
            with open(self.html_file, "r") as f:
                html_content = f.read()

            # Update the values
            html_content = html_content.replace(
                f'id="video-file">{state["video_file"]}</span>',
                f'id="video-file">{state["video_file"]}</span>',
            )
            html_content = html_content.replace(
                f'id="current-time" class="highlight">{state["current_time"]:.1f}s</span>',
                f'id="current-time" class="highlight">{state["current_time"]:.1f}s</span>',
            )
            html_content = html_content.replace(
                f'id="total-time">{state["total_time"]:.1f}s</span>',
                f'id="total-time">{state["total_time"]:.1f}s</span>',
            )
            html_content = html_content.replace(
                f'id="video-position">{state["video_position"] or "N/A"}</span>',
                f'id="video-position">{state["video_position"] or "N/A"}</span>',
            )
            html_content = html_content.replace(
                f'id="session-time">{state["session_time"]:.1f}s</span>',
                f'id="session-time">{state["session_time"]:.1f}s</span>',
            )
            html_content = html_content.replace(
                f'id="leader-mode" class="{"success" if state["is_leader"] else "info"}">{"Yes" if state["is_leader"] else "No"}</span>',
                f'id="leader-mode" class="{"success" if state["is_leader"] else "info"}">{"Yes" if state["is_leader"] else "No"}</span>',
            )

            # MIDI current/next removed - now only using comprehensive Recent/Upcoming lists

            # Update timestamp
            html_content = html_content.replace(
                f'id="timestamp">{time.strftime("%H:%M:%S")}</span>',
                f'id="timestamp">{time.strftime("%H:%M:%S")}</span>',
            )

            # Write updated HTML
            with open(self.html_file, "w") as f:
                f.write(html_content)

        except Exception as e:
            log_error(f"Error updating HTML: {e}", component="overlay")

    def cleanup(self):
        """Clean up resources"""
        self.running = False
        if hasattr(self, "update_thread"):
            self.update_thread.join(timeout=1)

        # Clean up HTML directory
        try:
            html_dir = Path(self.html_file).parent
            if html_dir.exists():
                import shutil

                shutil.rmtree(html_dir)
                log_info(f"Cleaned up HTML directory: {html_dir}", component="overlay")
        except Exception as e:
            log_warning(f"Could not remove HTML directory: {e}", component="overlay")

        # Reset Firefox flag
        self.firefox_opened = False
        log_info("HTML overlay cleaned up", component="overlay")

    def open_in_browser(self):
        """Open the HTML file in the default browser"""
        try:
            # Prevent multiple Firefox instances
            if self.firefox_opened:
                log_info(
                    "Firefox already opened, skipping duplicate launch",
                    component="overlay",
                )
                return

            # Simple browser open without blocking
            import subprocess
            import threading
            import time

            # Kill any existing Firefox processes first to avoid tab accumulation
            try:
                subprocess.run(["pkill", "-f", "firefox"], check=False, timeout=5)
                time.sleep(1)  # Give it time to close
                self.firefox_opened = False  # Reset flag after killing
            except:
                pass

            # Create a temporary Firefox profile directory
            profile_dir = "/tmp/firefox-debug-profile"
            import os

            os.makedirs(profile_dir, exist_ok=True)

            # Open Firefox with the profile (non-blocking)
            subprocess.Popen(
                [
                    "firefox",
                    "--new-instance",
                    "--new-window",
                    "--profile",
                    profile_dir,
                    f"file://{self.html_file}",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            # Mark Firefox as opened
            self.firefox_opened = True
            log_info("Firefox launched successfully", component="overlay")

            # Position window after a longer delay (in background thread)
            def position_window():
                time.sleep(
                    20
                )  # Wait longer for Firefox to fully load before positioning
                try:
                    # Get list of all windows and find Firefox
                    result = subprocess.run(
                        ["wmctrl", "-l"], capture_output=True, text=True, timeout=10
                    )

                    if result.returncode == 0:
                        firefox_window_id = None
                        for line in result.stdout.strip().split("\n"):
                            if line and (
                                "firefox" in line.lower()
                                or "kitchensync" in line.lower()
                            ):
                                # Make sure it's not a VLC window
                                if (
                                    "vlc" not in line.lower()
                                    and "media player" not in line.lower()
                                ):
                                    window_id = line.split()[0]
                                    firefox_window_id = window_id
                                    log_info(f"Found Firefox window: {line.strip()}")
                                    break

                        if firefox_window_id:
                            # Position using window ID instead of title
                            pos_result = subprocess.run(
                                [
                                    "wmctrl",
                                    "-i",
                                    "-r",
                                    firefox_window_id,
                                    "-e",
                                    "0,1280,0,640,1080",
                                ],
                                check=False,
                                timeout=5,
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL,
                            )
                            if pos_result.returncode == 0:
                                log_info(
                                    f"Positioned Firefox window on right side using window ID: {firefox_window_id}"
                                )
                            else:
                                log_warning(
                                    f"Failed to position Firefox window with ID: {firefox_window_id}"
                                )
                        else:
                            log_warning("Could not find Firefox window in wmctrl list")
                    else:
                        log_warning("Failed to get window list from wmctrl")

                except Exception as e:
                    log_warning(f"Failed to position Firefox window: {e}")

            threading.Thread(target=position_window, daemon=True).start()

            log_info(f"HTML debug overlay opened in browser: {self.html_file}")
        except Exception as e:
            log_error(f"Failed to open HTML overlay in browser: {e}")

    def update_content(self, system_info: dict = None):
        """Update the HTML content with current system information using templates"""
        try:
            if system_info is None:
                system_info = self._get_system_info()

            # Render using template system
            new_html_file = self.template_manager.render_debug_overlay(
                self.pi_id, system_info
            )

            if new_html_file:
                self.html_file = new_html_file
                log_info(
                    f"HTML debug overlay content updated: {self.html_file}",
                    component="overlay",
                )
            else:
                log_warning(
                    "Template rendering returned empty file path", component="overlay"
                )

        except Exception as e:
            log_error(
                f"Failed to update HTML overlay content: {e}", component="overlay"
            )

    def _get_system_info(self) -> dict:
        """Get current system information for the overlay"""
        try:
            import subprocess
            import psutil
            from datetime import datetime

            info = {
                "pi_id": self.pi_id,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "service_status": "Unknown",
                "service_status_class": "warning",
                "service_pid": "Unknown",
                "service_uptime": "Unknown",
                "vlc_status": "Unknown",
                "vlc_status_class": "warning",
                "video_file": "None",
                "vlc_process": "None",
                "recent_logs": "No logs available",
                "vlc_logs": "No VLC logs available",
            }

            # Check service status
            try:
                result = subprocess.run(
                    ["systemctl", "is-active", "kitchensync.service"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    info["service_status"] = "Active (running)"
                    info["service_status_class"] = "good"
                else:
                    info["service_status"] = "Inactive"
                    info["service_status_class"] = "error"
            except Exception:
                info["service_status"] = "Check failed"
                info["service_status_class"] = "error"

            # Get service PID and uptime
            try:
                result = subprocess.run(
                    [
                        "systemctl",
                        "show",
                        "kitchensync.service",
                        "--property=MainPID,ActiveEnterTimestamp",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    for line in result.stdout.split("\n"):
                        if "MainPID=" in line:
                            pid = line.split("=")[1].strip()
                            if pid != "0":
                                info["service_pid"] = pid
                                # Get process uptime
                                try:
                                    proc = psutil.Process(int(pid))
                                    uptime = datetime.now() - datetime.fromtimestamp(
                                        proc.create_time()
                                    )
                                    info["service_uptime"] = str(uptime).split(".")[0]
                                except:
                                    info["service_uptime"] = "Unknown"
            except Exception:
                pass

                # Check VLC process - VLC runs via Python bindings, not separate process
            try:
                # VLC runs embedded in Python, so look for the main Python process
                vlc_found = False
                vlc_pid = None

                # Check if our main process (which contains VLC) is running
                main_result = subprocess.run(
                    ["pgrep", "-f", "leader.py"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )

                log_info(
                    f"pgrep leader.py result: returncode={main_result.returncode}, stdout='{main_result.stdout.strip()}'",
                    component="overlay",
                )

                if main_result.returncode == 0:
                    # Main process is running, check if VLC is active within it
                    vlc_pid = main_result.stdout.strip().split("\n")[0]
                    log_info(
                        f"Found leader.py process with PID: {vlc_pid}",
                        component="overlay",
                    )

                    # If we have a video player reference and can get video info, VLC is running
                    try:
                        if self.video_player and hasattr(
                            self.video_player, "get_video_info"
                        ):
                            # Try to get video info - if this works, VLC is definitely running
                            video_info = self.video_player.get_video_info()
                            if (
                                video_info["total_time"] > 0
                                or video_info["current_time"] >= 0
                            ):
                                vlc_found = True
                                log_info(
                                    "VLC detected as active (video player responsive)",
                                    component="overlay",
                                )
                            else:
                                log_info(
                                    "VLC player exists but no video info available",
                                    component="overlay",
                                )
                        else:
                            # Fallback to log file check (old method)
                            from src.core.logger import log_file_paths
                            import time

                            paths = log_file_paths()

                            if os.path.exists(paths["vlc_main"]):
                                stat = os.stat(paths["vlc_main"])
                                age_seconds = time.time() - stat.st_mtime
                                log_info(
                                    f"VLC log file exists, age: {age_seconds:.1f} seconds",
                                    component="overlay",
                                )

                                if (
                                    age_seconds < 300
                                ):  # Extended to 5 minutes instead of 1 minute
                                    vlc_found = True
                                    log_info(
                                        "VLC detected as active (log file method)",
                                        component="overlay",
                                    )
                                else:
                                    log_info(
                                        "VLC log file too old, considering inactive",
                                        component="overlay",
                                    )
                            else:
                                log_info(
                                    "VLC log file does not exist", component="overlay"
                                )

                    except Exception as e:
                        log_error(
                            f"Error checking VLC status: {e}", component="overlay"
                        )
                else:
                    log_info("leader.py process not found", component="overlay")

                if vlc_found and vlc_pid:
                    info["vlc_status"] = f"Running (embedded in PID: {vlc_pid})"
                    info["vlc_status_class"] = "good"
                    info["vlc_process"] = f"Python VLC bindings in PID: {vlc_pid}"

                    # Get video playback information directly from video player
                    try:
                        if self.video_player and hasattr(
                            self.video_player, "get_video_info"
                        ):
                            video_info = self.video_player.get_video_info()
                            log_info(
                                f"Raw video info from player: {video_info}",
                                component="overlay",
                            )
                            info["video_current_time"] = video_info["current_time"]
                            info["video_total_time"] = video_info["total_time"]
                            info["video_position"] = video_info["position"]
                            info["video_state"] = video_info["state"]
                            info["video_loop_count"] = video_info.get("loop_count", 0)
                            info["looping_enabled"] = video_info.get(
                                "looping_enabled", False
                            )

                            # Get video file - prioritize state from update_debug_info
                            with self.state_lock:
                                state_video_file = self.state.get("video_file", "None")

                            # Get video file - prioritize state from update_debug_info
                            try:
                                if (
                                    state_video_file
                                    and state_video_file != "No video"
                                    and state_video_file != "None"
                                ):
                                    info["video_file"] = os.path.basename(
                                        state_video_file
                                    )
                                # Otherwise try to get from video player
                                elif (
                                    hasattr(self.video_player, "video_file")
                                    and self.video_player.video_file
                                ):
                                    info["video_file"] = os.path.basename(
                                        self.video_player.video_file
                                    )
                                elif (
                                    hasattr(self.video_player, "current_video")
                                    and self.video_player.current_video
                                ):
                                    info["video_file"] = os.path.basename(
                                        self.video_player.current_video
                                    )
                                else:
                                    info["video_file"] = "None"
                            except Exception as e:
                                log_error(
                                    f"Error getting video file name: {e}",
                                    component="overlay",
                                )
                                info["video_file"] = "Error getting filename"

                            log_info(
                                f"Video info: {video_info['current_time']:.1f}s / {video_info['total_time']:.1f}s ({video_info['state']}) - {info.get('video_file', 'No file')}",
                                component="overlay",
                            )
                        else:
                            # No video player reference - use state info
                            with self.state_lock:
                                info["video_current_time"] = self.state.get(
                                    "current_time", 0.0
                                )
                                info["video_total_time"] = self.state.get(
                                    "total_time", 0.0
                                )
                                info["video_position"] = self.state.get(
                                    "video_position", 0.0
                                )
                                info["video_state"] = "unknown"
                                info["video_file"] = self.state.get(
                                    "video_file", "None"
                                )
                            info["video_loop_count"] = 0
                            info["looping_enabled"] = False

                        # Get MIDI loop information if available
                        if hasattr(self, "midi_scheduler") and self.midi_scheduler:
                            midi_stats = self.midi_scheduler.get_stats()
                            info["midi_loop_count"] = midi_stats.get("loop_count", 0)
                        else:
                            info["midi_loop_count"] = 0
                            info["video_total_time"] = 0.0
                            info["video_position"] = 0.0
                            info["video_state"] = "no_player"
                            log_warning(
                                "No video player reference available",
                                component="overlay",
                            )
                    except Exception as e:
                        log_error(f"Error getting video info: {e}", component="overlay")
                        info["video_current_time"] = 0.0
                        info["video_total_time"] = 0.0
                        info["video_position"] = 0.0
                        info["video_state"] = "error"
                else:
                    info["vlc_status"] = "Not running (Python VLC not detected)"
                    info["vlc_status_class"] = "error"
                    info["video_current_time"] = 0.0
                    info["video_total_time"] = 0.0
                    info["video_position"] = 0.0
                    info["video_state"] = "stopped"

            except Exception as e:
                info["vlc_status"] = f"Check failed: {e}"
                info["vlc_status_class"] = "warning"

            # Get MIDI information if available
            try:
                if hasattr(self, "midi_scheduler") and self.midi_scheduler:
                    if hasattr(self.midi_scheduler, "get_recent_cues"):
                        info["midi_recent"] = self.midi_scheduler.get_recent_cues(
                            info.get("video_current_time", 0), lookback=10.0
                        )
                    if hasattr(self.midi_scheduler, "get_upcoming_cues"):
                        info["midi_upcoming"] = self.midi_scheduler.get_upcoming_cues(
                            info.get("video_current_time", 0), lookahead=15.0
                        )
                else:
                    info["midi_recent"] = []
                    info["midi_upcoming"] = []
            except Exception as e:
                log_warning(f"Error getting MIDI info: {e}", component="overlay")
                info["midi_recent"] = []
                info["midi_upcoming"] = []

            # Get recent logs
            try:
                from src.core.logger import log_file_paths

                paths = log_file_paths()
                log_info(f"Log paths: {paths}", component="overlay")

                # Recent system logs
                system_path = paths["system"]
                if system_path and os.path.exists(system_path):
                    try:
                        with open(system_path, "r") as f:
                            lines = f.readlines()
                            recent = lines[-20:] if len(lines) > 20 else lines
                            info["recent_logs"] = "".join(recent)
                            log_info(
                                f"Read {len(recent)} lines from system log",
                                component="overlay",
                            )
                    except Exception as e:
                        info["recent_logs"] = f"Error reading system log: {e}"
                        log_error(f"Error reading system log: {e}", component="overlay")
                else:
                    log_warning(
                        f"System log file not found: {system_path}",
                        component="overlay",
                    )
                    info["recent_logs"] = "System log file not found"

                # Recent VLC logs
                vlc_path = paths["vlc_main"]
                if vlc_path and os.path.exists(vlc_path):
                    try:
                        with open(vlc_path, "r") as f:
                            lines = f.readlines()
                            recent = lines[-20:] if len(lines) > 20 else lines
                            info["vlc_logs"] = "".join(recent)
                            log_info(
                                f"Read {len(recent)} lines from VLC log",
                                component="overlay",
                            )
                    except Exception as e:
                        info["vlc_logs"] = f"Error reading VLC log: {e}"
                        log_error(f"Error reading VLC log: {e}", component="overlay")
                else:
                    log_warning(
                        f"VLC log file not found: {vlc_path}",
                        component="overlay",
                    )
                    info["vlc_logs"] = "VLC log file not found"

            except Exception as e:
                log_error(f"Error reading log files: {e}", component="overlay")
                info["recent_logs"] = f"Error reading logs: {e}"
                info["vlc_logs"] = f"Error reading logs: {e}"

            return info

        except Exception as e:
            log_error(f"Failed to get system info: {e}")
            return {
                "pi_id": self.pi_id,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "error": f"Failed to get system info: {e}",
            }


class HTMLDebugManager:
    """Manages the HTML debug overlay"""

    def __init__(self, pi_id: str, video_player=None, midi_scheduler=None):
        self.overlay = HTMLDebugOverlay(pi_id, video_player)
        self.overlay.midi_scheduler = midi_scheduler  # Pass MIDI scheduler to overlay
        self.midi_scheduler = midi_scheduler
        self.update_thread = None
        self.running = False

    def start(self):
        """Start the HTML debug overlay"""
        try:
            # Open in browser
            self.overlay.open_in_browser()

            # Start update thread
            self.running = True
            self.update_thread = threading.Thread(target=self._update_loop, daemon=True)
            self.update_thread.start()

            log_info("HTML debug manager created", component="overlay")
        except Exception as e:
            log_error(f"Failed to start HTML debug manager: {e}", component="overlay")

    def stop(self):
        """Stop the HTML debug overlay"""
        self.running = False
        if self.update_thread:
            self.update_thread.join(timeout=1)
        log_info("HTML debug manager stopped", component="overlay")

    def update_debug_info(
        self,
        video_file: str,
        current_time: float,
        total_time: float,
        session_time: float,
        video_position: Optional[float],
        current_cues: list,
        upcoming_cues: list,
        video_loop_count: int = 0,
        midi_loop_count: int = 0,
        looping_enabled: bool = True,
    ):
        """Update debug information - compatibility method for the debug system"""
        try:
            # Update overlay state (removed redundant midi_current/midi_next processing)
            self.overlay.update_state(
                video_file=video_file,
                current_time=current_time,
                total_time=total_time,
                session_time=session_time,
                video_position=video_position,
                midi_recent=current_cues[-5:] if current_cues else [],
                midi_upcoming=upcoming_cues[:5] if upcoming_cues else [],
                video_loop_count=video_loop_count,
                midi_loop_count=midi_loop_count,
                looping_enabled=looping_enabled,
            )

            log_info(
                f"Debug info updated: {video_file}, {current_time:.1f}s",
                component="overlay",
            )

        except Exception as e:
            log_error(f"Error updating debug info: {e}", component="overlay")

    def cleanup(self):
        """Clean up resources"""
        self.stop()
        if self.overlay:
            self.overlay.cleanup()

    def _update_loop(self):
        """Update loop for the HTML overlay"""
        while self.running:
            try:
                # Update the HTML content with current system info
                self.overlay.update_content()
                time.sleep(5)  # Update every 5 seconds
            except Exception as e:
                log_error(f"Error in HTML update loop: {e}", component="overlay")
                time.sleep(5)  # Continue trying
