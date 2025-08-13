#!/usr/bin/env python3
"""
HTML-based debug overlay for KitchenSync
Opens a browser window with live-updating debug information
"""

import os
import shutil
import subprocess
import time
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

try:
    import psutil
except ImportError:
    psutil = None
from src.core.logger import (
    debug_log_info,
    log_error,
    debug_log_warning,
    debug_log_error,
    _ENABLE_SYSTEM_LOGGING,
)


from src.debug.template_engine import DebugTemplateManager
from src.ui.window_manager import WindowManager


def _tail_log_file(file_path: str, max_lines: int = 10) -> list:
    """Efficiently read only the last N lines from a log file without loading entire file"""
    try:
        if not os.path.exists(file_path):
            return []

        # Get file size first to avoid reading huge files
        file_size = os.path.getsize(file_path)
        if file_size == 0:
            return []

        # For very large files (>1MB), use efficient tail approach
        if file_size > 1024 * 1024:  # 1MB threshold
            try:
                # Use system tail command for efficiency on large files
                result = subprocess.run(
                    ["tail", "-n", str(max_lines), file_path],
                    capture_output=True,
                    text=True,
                    timeout=2,
                )
                if result.returncode == 0:
                    return (
                        result.stdout.strip().split("\n")
                        if result.stdout.strip()
                        else []
                    )
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass  # Fall back to Python method

        # For smaller files or if tail command fails, read efficiently
        with open(file_path, "r") as f:
            # Seek to end and read backwards for efficiency
            lines = []
            f.seek(0, 2)  # Seek to end
            file_length = f.tell()

            # Don't read more than 64KB from end for performance
            read_size = min(65536, file_length)
            f.seek(max(0, file_length - read_size))

            content = f.read()
            all_lines = content.split("\n")

            # Get last N non-empty lines
            non_empty_lines = [line for line in all_lines if line.strip()]
            return (
                non_empty_lines[-max_lines:]
                if len(non_empty_lines) > max_lines
                else non_empty_lines
            )

    except Exception as e:
        return [f"Error reading {file_path}: {e}"]


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
        self.firefox_process = None

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

            debug_log_info(f"HTML debug file created: {self.html_file}")

        except Exception as e:
            log_error(f"Failed to create HTML file using templates: {e}")
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

            debug_log_warning(f"Created fallback HTML file: {self.html_file}")

        except Exception as e:
            log_error(f"Failed to create fallback HTML: {e}")

    def _setup_debug_environment(self):
        """Creates the debug directory and copies static files once."""
        try:
            overlay_dir = Path(self.html_file).parent
            overlay_dir.mkdir(exist_ok=True)
            self.template_manager.copy_static_files(overlay_dir)
            debug_log_info("Debug environment setup complete.")
        except Exception as e:
            log_error(f"Failed to set up debug environment: {e}")

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
                log_error(f"HTML update error: {e}")
                time.sleep(5)

    def cleanup(self):
        """Clean up resources"""
        debug_log_info("Cleaning up HTML debug overlay")

        # Stop the main thread first
        self.running = False

        # Gracefully terminate Firefox process if we launched it
        if self.firefox_process:
            try:
                debug_log_info("Terminating Firefox process gracefully")
                self.firefox_process.terminate()

                # Wait up to 3 seconds for graceful shutdown
                try:
                    self.firefox_process.wait(timeout=3)
                    debug_log_info("Firefox process terminated gracefully")
                except subprocess.TimeoutExpired:
                    debug_log_warning(
                        "Firefox didn't exit gracefully, forcing termination"
                    )
                    self.firefox_process.kill()
                    self.firefox_process.wait()

            except Exception as e:
                debug_log_warning(f"Error terminating Firefox process: {e}")
            finally:
                self.firefox_process = None

        # Clean up profile directory
        try:
            profile_dir = "/tmp/ff-clean-profile"
            if os.path.exists(profile_dir):
                shutil.rmtree(profile_dir)
                debug_log_info(f"Removed profile directory: {profile_dir}")
        except Exception as e:
            debug_log_warning(f"Could not remove profile directory: {e}")

        # Stop the update thread
        if self.update_thread and self.update_thread.is_alive():
            self.stop_update = True
            self.update_thread.join(timeout=5)
            if self.update_thread.is_alive():
                debug_log_warning("Update thread did not stop gracefully")

        # Clean up HTML directory
        try:
            html_dir = Path(self.html_file).parent
            if html_dir.exists():
                shutil.rmtree(html_dir)
                debug_log_info(f"Cleaned up HTML directory: {html_dir}")
        except Exception as e:
            debug_log_warning(f"Could not remove HTML directory: {e}")

        # Reset Firefox state
        self.firefox_opened = False
        self.firefox_process = None

        debug_log_info("HTML debug overlay cleanup completed")

    def open_in_browser(self):
        """Open the HTML file in the default browser"""
        try:
            # Prevent multiple Firefox instances
            if self.firefox_opened:
                debug_log_info("Firefox already opened, skipping duplicate launch")
                return

            # Simple browser open without blocking
            # Simple clean profile approach
            profile_dir = "/tmp/ff-clean-profile"

            # Remove existing profile directory if it exists
            if os.path.exists(profile_dir):
                shutil.rmtree(profile_dir)

            # Create fresh profile directory
            os.makedirs(profile_dir, exist_ok=True)

            # Create user.js to suppress Firefox Privacy Notice and welcome screens
            userjs_path = os.path.join(profile_dir, "user.js")
            try:
                with open(userjs_path, "w") as f:
                    f.write(
                        """// Firefox user.js to suppress Privacy Notice and welcome screens
// This ensures a completely clean launch without popups or extra tabs

// Disable privacy notice tab
user_pref("toolkit.telemetry.reportingpolicy.firstRun", false);
user_pref("datareporting.policy.dataSubmissionPolicyBypassNotification", true);

// Suppress welcome/onboarding pages
user_pref("trailhead.firstrun.didSeeAboutWelcome", true);
user_pref("browser.aboutwelcome.enabled", false);
user_pref("startup.homepage_welcome_url", "");
user_pref("browser.startup.homepage_override.mstone", "ignore");

// Disable telemetry and data collection
user_pref("toolkit.telemetry.enabled", false);
user_pref("toolkit.telemetry.unified", false);
user_pref("browser.ping-centre.telemetry", false);

// Force clean startup
user_pref("browser.startup.page", 0);
user_pref("browser.startup.homepage", "about:blank");
user_pref("browser.newtabpage.enabled", false);
user_pref("browser.sessionstore.enabled", false);
user_pref("browser.sessionstore.resume_from_crash", false);

// Disable activity stream and other startup features
user_pref("browser.newtabpage.activity-stream.enabled", false);
user_pref("browser.newtabpage.activity-stream.default.sites", "");
"""
                    )
                debug_log_info("Created user.js to suppress Firefox welcome screens")
            except Exception as e:
                debug_log_warning(f"Could not create user.js: {e}")

            # Also create policies.json for enterprise-level suppression (more effective)
            policies_path = os.path.join(profile_dir, "policies.json")
            try:
                with open(policies_path, "w") as f:
                    f.write(
                        """{
  "policies": {
    "OverrideFirstRunPage": "",
    "OverridePostUpdatePage": "",
    "DisableFirefoxStudies": true,
    "DisablePocket": true,
    "DisableTelemetry": true,
    "DisableFirefoxAccounts": true,
    "DisableProfileImport": true,
    "DisablePasswordReveal": true,
    "DisableFormHistory": true,
    "DisableBookmarks": true,
    "DisableDeveloperTools": false,
    "DisableFirefoxScreenshots": true
  }
}"""
                    )
                debug_log_info(
                    "Created policies.json for enterprise-level Firefox suppression"
                )
            except Exception as e:
                debug_log_warning(f"Could not create policies.json: {e}")

            # Get current user for environment setup
            current_user = os.getenv("USER", "kitchensync")

            # Force Firefox to use X11 (prevent Wayland fallback)
            firefox_env = os.environ.copy()
            firefox_env.update(
                {
                    "DISPLAY": ":0",
                    "XAUTHORITY": f"/home/{current_user}/.Xauthority",
                    "XDG_RUNTIME_DIR": f"/run/user/{os.getuid()}",
                    "HOME": f"/home/{current_user}",
                    # CRITICAL: Force X11 mode and disable Wayland
                    "XDG_SESSION_TYPE": "x11",
                    "GDK_BACKEND": "x11",
                    "QT_QPA_PLATFORM": "xcb",
                    "WAYLAND_DISPLAY": "",
                    # Force Firefox to use X11 backend
                    "MOZ_ENABLE_WAYLAND": "0",
                    "MOZ_DISABLE_WAYLAND": "1",
                    "MOZ_ENABLE_X11": "1",
                    "MOZ_X11_EGL": "1",
                }
            )

            debug_log_info(
                f"Launching Firefox with environment: USER={current_user}, DISPLAY={firefox_env.get('DISPLAY')}, XAUTHORITY={firefox_env.get('XAUTHORITY')}"
            )

            # Launch Firefox and capture any errors
            try:
                self.firefox_process = subprocess.Popen(
                    [
                        "firefox",
                        "--no-remote",
                        "--profile",
                        profile_dir,
                        "--new-instance",
                        f"file://{self.html_file}",
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env=firefox_env,
                )

                # Check if Firefox started successfully (don't wait for completion)
                time.sleep(0.5)
                if self.firefox_process.poll() is not None:
                    # Process exited, capture error
                    stdout, stderr = self.firefox_process.communicate()
                    log_error(
                        f"Firefox failed to start. Exit code: {self.firefox_process.returncode}"
                    )
                    log_error(f"Firefox stdout: {stdout.decode()}")
                    log_error(f"Firefox stderr: {stderr.decode()}")

                    # Try fallback launch without some options
                    debug_log_info("Trying Firefox fallback launch...")
                    try:
                        self.firefox_process = subprocess.Popen(
                            [
                                "firefox",
                                "--new-instance",
                                "--new-window",
                                "--profile",
                                profile_dir,
                                f"file://{self.html_file}",
                            ],
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            env=firefox_env,
                        )

                        time.sleep(0.5)
                        if fallback_process.poll() is not None:
                            stdout, stderr = fallback_process.communicate()
                            log_error(
                                f"Firefox fallback also failed: {stderr.decode()}"
                            )
                            return
                        else:
                            process = fallback_process
                            debug_log_info("Firefox fallback launch successful")
                    except Exception as fallback_e:
                        log_error(f"Firefox fallback launch failed: {fallback_e}")
                        return

            except Exception as e:
                log_error(f"Exception launching Firefox: {e}")
                return

            # Mark Firefox as opened
            self.firefox_opened = True
            debug_log_info("Firefox launched successfully")

            # Position window after a short delay (in background thread)
            def position_window():
                debug_log_info("Starting to wait for Firefox window...")

                # Wait for Firefox window to appear
                firefox_window = self.window_manager.wait_for_window(
                    search_terms=["firefox", "kitchensync debug"],
                    exclude_terms=["vlc", "media player"],
                    timeout=30,
                )

                if firefox_window:
                    debug_log_info(f"Found Firefox window: {firefox_window}")

                    # Get display geometry for better positioning
                    display_width, display_height = (
                        self.window_manager.get_display_geometry()
                    )
                    debug_log_info(
                        f"Display geometry: {display_width}x{display_height}"
                    )

                    # Calculate positioning based on display size
                    # Position Firefox on right side with proper coordinates
                    firefox_x = max(0, display_width - 640)  # Right side, 640px wide
                    firefox_y = 0
                    firefox_width = 640
                    firefox_height = min(1080, display_height)

                    debug_log_info(
                        f"Target Firefox position: ({firefox_x}, {firefox_y}) {firefox_width}x{firefox_height}"
                    )

                    # Log current window positions
                    window_details = self.window_manager.get_window_details()
                    debug_log_info(
                        f"Current window positions before Firefox positioning:\n{window_details}"
                    )

                    # Position Firefox window
                    success = self.window_manager.position_window(
                        firefox_window,
                        firefox_x,
                        firefox_y,
                        firefox_width,
                        firefox_height,
                    )

                    if success:
                        debug_log_info("Positioned Firefox window on right side")

                        # Log positions after positioning
                        time.sleep(0.5)
                        after_details = self.window_manager.get_window_details()
                        debug_log_info(
                            f"Window positions after Firefox positioning:\n{after_details}"
                        )
                    else:
                        debug_log_warning("Failed to position Firefox window")
                else:
                    debug_log_warning("Firefox window not found for positioning")

            threading.Thread(target=position_window, daemon=True).start()

            debug_log_info(f"HTML debug overlay opened in browser: {self.html_file}")
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
                            debug_log_info(
                                f"HTML debug overlay content updated: {self.html_file}",
                                component="overlay",
                            )
                        else:
                            debug_log_warning(
                                f"Generated HTML file too small ({len(content)} chars), keeping previous version",
                                component="overlay",
                            )
                except Exception as read_error:
                    debug_log_warning(
                        f"Could not verify new HTML file: {read_error}",
                        component="overlay",
                    )
            else:
                debug_log_warning(
                    "Template rendering returned empty or missing file path",
                    component="overlay",
                )

        except Exception as e:
            log_error(f"Failed to update HTML overlay content: {e}")
            # Don't update html_file on error - keep the previous working version

    def _get_system_info(self) -> dict:
        """Get current system information for the overlay"""
        try:

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

                debug_log_info(
                    f"pgrep leader.py result: returncode={main_result.returncode}, stdout='{main_result.stdout.strip()}'",
                    component="overlay",
                )

                if main_result.returncode == 0:
                    # Main process is running, check if VLC is active within it
                    vlc_pid = main_result.stdout.strip().split("\n")[0]
                    debug_log_info(
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
                                debug_log_info(
                                    "VLC detected as active (video player responsive)",
                                    component="overlay",
                                )
                            else:
                                debug_log_info(
                                    "VLC player exists but no video info available",
                                    component="overlay",
                                )
                        else:
                            # Fallback to log file check (old method)
                            from src.core.logger import log_file_paths

                            paths = log_file_paths()

                            if os.path.exists(paths["vlc_main"]):
                                stat = os.stat(paths["vlc_main"])
                                age_seconds = time.time() - stat.st_mtime
                                debug_log_info(
                                    f"VLC log file exists, age: {age_seconds:.1f} seconds",
                                    component="overlay",
                                )

                                if (
                                    age_seconds < 300
                                ):  # Extended to 5 minutes instead of 1 minute
                                    vlc_found = True
                                    debug_log_info(
                                        "VLC detected as active (log file method)",
                                        component="overlay",
                                    )
                                else:
                                    debug_log_info(
                                        "VLC log file too old, considering inactive",
                                        component="overlay",
                                    )
                            else:
                                debug_log_info("VLC log file does not exist")

                    except Exception as e:
                        log_error(f"Error checking VLC status: {e}")
                else:
                    debug_log_info("leader.py process not found")

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
                            debug_log_info(
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

                            debug_log_info(
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
                            debug_log_warning(
                                "No video player reference available",
                                component="overlay",
                            )
                    except Exception as e:
                        log_error(f"Error getting video info: {e}")
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
                debug_log_warning(f"Error getting MIDI info: {e}")
                info["midi_recent"] = []
                info["midi_upcoming"] = []

            # Get recent logs ONLY if system logging is enabled
            if _ENABLE_SYSTEM_LOGGING:
                try:
                    from src.core.logger import log_file_paths

                    paths = log_file_paths()
                    debug_log_info(f"Log paths: {paths}")

                    # Recent system logs - use efficient tailing (only last 10 lines)
                    system_path = paths["system"]
                    if system_path and os.path.exists(system_path):
                        recent_lines = _tail_log_file(system_path, max_lines=10)
                        info["recent_logs"] = "\n".join(recent_lines)
                        debug_log_info(
                            f"Read {len(recent_lines)} lines from system log"
                        )
                    else:
                        info["recent_logs"] = "System log file not found"

                    # Recent VLC logs - use efficient tailing (only last 10 lines)
                    vlc_path = paths["vlc_main"]
                    if vlc_path and os.path.exists(vlc_path):
                        recent_lines = _tail_log_file(vlc_path, max_lines=10)
                        info["vlc_logs"] = "\n".join(recent_lines)
                        debug_log_info(f"Read {len(recent_lines)} lines from VLC log")
                    else:
                        info["vlc_logs"] = "VLC log file not found"

                except Exception as e:
                    log_error(f"Error reading log files: {e}")
                    info["recent_logs"] = f"Error reading logs: {e}"
                    info["vlc_logs"] = f"Error reading logs: {e}"
            else:
                # When logging is disabled, don't read or display logs
                info["recent_logs"] = "Logging disabled for performance"
                info["vlc_logs"] = "Logging disabled for performance"

            # Generate log sections HTML conditionally
            if _ENABLE_SYSTEM_LOGGING:
                info[
                    "log_sections_html"
                ] = f"""
                <div class="log-section">
                    <h3>Recent System Log (Last 10 entries)</h3>
                    <div class="log-content">{info["recent_logs"]}</div>
                </div>

                <div class="log-section">
                    <h3>Recent VLC Log (Last 10 entries)</h3>
                    <div class="log-content">{info["vlc_logs"]}</div>
                </div>
                """
            else:
                info[
                    "log_sections_html"
                ] = """
                <div class="info-section">
                    <h3>📈 Performance Mode</h3>
                    <p>Logging disabled for optimal performance. Enable <code>enable_system_logging=true</code> and <code>enable_vlc_logging=true</code> in config to show logs.</p>
                </div>
                """

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

    def start(self):
        """Start the HTML debug overlay"""
        try:
            # Open in browser
            self.overlay.open_in_browser()

            debug_log_info("HTML debug manager started")
        except Exception as e:
            log_error(f"Failed to start HTML debug manager: {e}")

    def stop(self):
        """Stop the HTML debug overlay"""
        debug_log_info("Stopping HTML debug overlay")
        self.cleanup()

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

            debug_log_info(
                f"Debug info updated: {video_file}, {current_time:.1f}s",
                component="overlay",
            )

        except Exception as e:
            log_error(f"Error updating debug info: {e}")

    def cleanup(self):
        """Clean up resources"""
        self.stop()
        if self.overlay:
            self.overlay.cleanup()
