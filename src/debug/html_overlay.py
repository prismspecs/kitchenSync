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
from src.ui.window_manager import WindowManager


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

        # Track Chromium state
        self.chromium_opened = False
        
        # Initialize window manager
        self.window_manager = WindowManager()

        # Create the debug directory and copy static files once
        self._setup_debug_environment()

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

    def _setup_debug_environment(self):
        """Creates the debug directory and copies static files once."""
        try:
            overlay_dir = Path(self.html_file).parent
            overlay_dir.mkdir(exist_ok=True)
            self.template_manager.copy_static_files(overlay_dir)
            log_info("Debug environment setup complete.", component="overlay")
        except Exception as e:
            log_error(f"Failed to set up debug environment: {e}", component="overlay")

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
                self.update_content()
                time.sleep(5)  # Update every 5 seconds
            except Exception as e:
                log_error(f"HTML update error: {e}", component="overlay")
                time.sleep(5)

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

        # Reset Chromium flag
        self.chromium_opened = False
        log_info("HTML overlay cleaned up", component="overlay")

    def open_in_browser(self):
        """Open the HTML file in Chromium browser (much lighter than Firefox)"""
        try:
            # Prevent multiple Chromium instances
            if self.chromium_opened:
                log_info(
                    "Chromium already opened, skipping duplicate launch",
                    component="overlay",
                )
                return

            # Simple browser open without blocking
            import subprocess
            import threading
            import time

            # Kill any existing Chromium processes first to avoid tab accumulation
            try:
                subprocess.run(["pkill", "-f", "chromium"], check=False, timeout=3)
                time.sleep(0.2)  # Reduced wait time
                self.chromium_opened = False  # Reset flag after killing
            except:
                pass

            # Create a temporary Chromium profile directory
            profile_dir = "/tmp/chromium-debug-profile"
            import os

            os.makedirs(profile_dir, exist_ok=True)

            # Open Chromium with the profile (non-blocking)
            # Set up environment for Chromium in system service context
            current_user = os.getenv("USER", "kitchensync")
            
            chromium_env = os.environ.copy()
            chromium_env.update({
                'DISPLAY': ':0',
                'XDG_RUNTIME_DIR': f'/run/user/{os.getuid()}',
                'HOME': f'/home/{current_user}',
                # Force Chromium to use X11 instead of Wayland for better window management
                'WAYLAND_DISPLAY': '',
                'XDG_SESSION_TYPE': 'x11',
                'GDK_BACKEND': 'x11',
                'QT_QPA_PLATFORM': 'xcb',
                # Chromium-specific optimizations
                'CHROMIUM_FLAGS': '--disable-extensions --disable-plugins --disable-background-tabs --disable-background-mode --disable-background-networking --disable-default-apps --disable-sync --disable-translate --disable-web-security --no-first-run --no-default-browser-check --disable-features=VizDisplayCompositor',
            })
            
            log_info(f"Launching Chromium with environment: USER={current_user}, DISPLAY={chromium_env.get('DISPLAY')}, XDG_SESSION_TYPE={chromium_env.get('XDG_SESSION_TYPE')}", component="overlay")
            
            # Launch Chromium with optimized flags for speed and X11 compatibility
            try:
                process = subprocess.Popen(
                    [
                        "chromium-browser",
                        "--new-window",
                        "--user-data-dir=" + profile_dir,
                        "--no-first-run",
                        "--disable-extensions",
                        "--disable-plugins",
                        "--disable-background-tabs",
                        "--disable-background-mode",
                        "--disable-background-networking",
                        "--disable-default-apps",
                        "--disable-sync",
                        "--disable-translate",
                        "--disable-web-security",
                        "--no-default-browser-check",
                        "--disable-features=VizDisplayCompositor",
                        "--disable-gpu-sandbox",
                        "--disable-software-rasterizer",
                        "--disable-dev-shm-usage",
                        "--disable-ipc-flooding-protection",
                        "--disable-renderer-backgrounding",
                        "--disable-backgrounding-occluded-windows",
                        "--disable-background-timer-throttling",
                        "--disable-features=TranslateUI",
                        "--disable-features=NetworkService",
                        "--disable-features=NetworkServiceLogging",
                        # Force X11 mode
                        "--disable-ozone",
                        "--use-x11",
                        f"file://{self.html_file}",
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env=chromium_env,
                )
                
                # Check if Chromium started successfully (don't wait for completion)
                time.sleep(0.3)  # Reduced wait time
                if process.poll() is not None:
                    # Process exited, capture error
                    stdout, stderr = process.communicate()
                    log_error(f"Chromium failed to start. Exit code: {process.returncode}", component="overlay")
                    log_error(f"Chromium stdout: {stdout.decode()}", component="overlay")
                    log_error(f"Chromium stderr: {stderr.decode()}", component="overlay")
                    return
                    
            except Exception as e:
                log_error(f"Exception launching Chromium: {e}", component="overlay")
                return

            # Mark Chromium as opened
            self.chromium_opened = True
            log_info("Chromium launched successfully", component="overlay")

            # Position window after a short delay (in background thread)
            def position_window():
                log_info("Starting to wait for Chromium window...", component="overlay")
                
                # First, let's debug what windows are currently visible
                log_info("=== DEBUG: Current window list ===", component="overlay")
                all_windows = self.window_manager.list_windows()
                for i, window in enumerate(all_windows):
                    if window.strip():
                        log_info(f"Window {i}: {window}", component="overlay")
                log_info("=== END DEBUG ===", component="overlay")
                
                # Wait for Chromium window to appear (reduced timeout)
                # Use more flexible search terms for Wayland - the actual window name is "KitchenSync Debug"
                chromium_window = self.window_manager.wait_for_window(
                    search_terms=["kitchensync debug", "kitchensync", "debug", "chromium"],
                    exclude_terms=["vlc", "media player"],
                    timeout=5  # Reduced from 10s to 5s
                )

                if chromium_window:
                    log_info(f"Found Chromium window: {chromium_window}", component="overlay")
                    
                    # Get display geometry for better positioning
                    display_width, display_height = self.window_manager.get_display_geometry()
                    log_info(f"Display geometry: {display_width}x{display_height}", component="overlay")
                    
                    # Calculate positioning based on display size
                    # Position Chromium on right side with proper coordinates
                    chromium_x = max(0, display_width - 640)  # Right side, 640px wide
                    chromium_y = 0
                    chromium_width = 640
                    chromium_height = min(1080, display_height)
                    
                    log_info(f"Target Chromium position: ({chromium_x}, {chromium_y}) {chromium_width}x{chromium_height}", component="overlay")
                    
                    # Log current window positions
                    window_details = self.window_manager.get_window_details()
                    log_info(f"Current window positions before Chromium positioning:\n{window_details}", component="overlay")
                    
                    # Position Chromium window
                    success = self.window_manager.position_window(chromium_window, chromium_x, chromium_y, chromium_width, chromium_height)
                    
                    if success:
                        log_info("Positioned Chromium window on right side", component="overlay")
                        
                        # Log positions after positioning
                        time.sleep(0.5)
                        after_details = self.window_manager.get_window_details()
                        log_info(f"Window positions after Chromium positioning:\n{after_details}", component="overlay")
                    else:
                        log_warning("Failed to position Chromium window", component="overlay")
                        
                        # Try alternative positioning approach for Chromium
                        log_info("Trying alternative Chromium positioning...", component="overlay")
                        self._try_alternative_chromium_positioning(chromium_window, chromium_x, chromium_y, chromium_width, chromium_height)
                else:
                    log_warning("Chromium window not found for positioning", component="overlay")
                    
                    # Debug: show what windows we can see
                    log_info("=== DEBUG: Windows found after timeout ===", component="overlay")
                    final_windows = self.window_manager.list_windows()
                    for i, window in enumerate(final_windows):
                        if window.strip():
                            log_info(f"Window {i}: {window}", component="overlay")
                    log_info("=== END DEBUG ===", component="overlay")

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

            if new_html_file and os.path.exists(new_html_file):
                # Verify the file has content before updating
                try:
                    with open(new_html_file, "r") as f:
                        content = f.read()
                        if len(content.strip()) > 100:  # Ensure it's not empty/minimal
                            self.html_file = new_html_file
                            log_info(
                                f"HTML debug overlay content updated: {self.html_file}",
                                component="overlay",
                            )
                        else:
                            log_warning(
                                f"Generated HTML file too small ({len(content)} chars), keeping previous version",
                                component="overlay",
                            )
                except Exception as read_error:
                    log_warning(
                        f"Could not verify new HTML file: {read_error}",
                        component="overlay",
                    )
            else:
                log_warning(
                    "Template rendering returned empty or missing file path",
                    component="overlay",
                )

        except Exception as e:
            log_error(
                f"Failed to update HTML overlay content: {e}", component="overlay"
            )
            # Don't update html_file on error - keep the previous working version

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

            # Check service status (user service, not system service)
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

            # Get service PID and uptime (user service)
            try:
                result = subprocess.run(
                    [
                        "systemctl",
                        "--user",
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
                    info["vlc_status"] = "Running"
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

    def _try_alternative_chromium_positioning(self, window_id, x, y, width, height):
        """Try alternative methods to position Chromium window"""
        try:
            log_info(f"Attempting alternative positioning for Chromium window {window_id}", component="overlay")
            
            # Method 1: Try using xdotool if available
            try:
                import subprocess
                result = subprocess.run(
                    ["xdotool", "search", "--name", "chromium", "windowmove", str(x), str(y)],
                    capture_output=True, timeout=5
                )
                if result.returncode == 0:
                    log_info("Successfully moved Chromium window with xdotool", component="overlay")
                    
                    # Now try to resize
                    resize_result = subprocess.run(
                        ["xdotool", "search", "--name", "chromium", "windowsize", str(width), str(height)],
                        capture_output=True, timeout=5
                    )
                    if resize_result.returncode == 0:
                        log_info("Successfully resized Chromium window with xdotool", component="overlay")
                        return True
                    else:
                        log_warning(f"xdotool resize failed: {resize_result.stderr.decode()}", component="overlay")
                else:
                    log_warning(f"xdotool move failed: {result.stderr.decode()}", component="overlay")
            except FileNotFoundError:
                log_info("xdotool not available, trying next method", component="overlay")
            
            # Method 2: Try using wmctrl with different approach
            try:
                import subprocess
                # First try to focus the window
                focus_result = subprocess.run(
                    ["wmctrl", "-ia", window_id], check=False, timeout=5, capture_output=True
                )
                if focus_result.returncode == 0:
                    log_info("Successfully focused Chromium window", component="overlay")
                
                # Try positioning with wmctrl using different format
                position_result = subprocess.run(
                    ["wmctrl", "-ir", window_id, "-e", f"0,{x},{y},{width},{height}"],
                    check=False, timeout=5, capture_output=True
                )
                if position_result.returncode == 0:
                    log_info("Alternative wmctrl positioning successful", component="overlay")
                    return True
                else:
                    log_warning(f"Alternative wmctrl failed: {position_result.stderr.decode()}", component="overlay")
                    
            except Exception as e:
                log_error(f"Alternative positioning failed: {e}", component="overlay")
            
            # Method 3: Try using xwininfo to get window info
            try:
                import subprocess
                info_result = subprocess.run(
                    ["xwininfo", "-id", window_id], capture_output=True, timeout=5
                )
                if info_result.returncode == 0:
                    log_info(f"Window info for {window_id}:\n{info_result.stdout.decode()}", component="overlay")
            except FileNotFoundError:
                log_info("xwininfo not available", component="overlay")
                
        except Exception as e:
            log_error(f"Alternative positioning methods failed: {e}", component="overlay")
        
        return False


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
        update_count = 0
        log_info("HTML update loop started", component="overlay")

        while self.running:
            try:
                update_count += 1
                log_info(f"HTML update #{update_count} starting", component="overlay")

                # Update the HTML content with current system info
                self.overlay.update_content()

                log_info(f"HTML update #{update_count} completed", component="overlay")
                time.sleep(5)  # Update every 5 seconds

            except Exception as e:
                log_error(
                    f"Error in HTML update loop #{update_count}: {e}",
                    component="overlay",
                )
                time.sleep(5)  # Continue trying

        log_info("HTML update loop stopped", component="overlay")
