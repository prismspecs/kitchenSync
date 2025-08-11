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


class HTMLDebugOverlay:
    """HTML-based debug overlay that opens in a browser window"""

    def __init__(self, pi_id: str):
        self.pi_id = pi_id
        self.running = True
        self.state_lock = threading.Lock()
        self.html_file = f"/tmp/kitchensync_debug_{pi_id}.html"

        # Initialize state
        self.state = {
            "video_file": "No video",
            "current_time": 0.0,
            "total_time": 0.0,
            "session_time": 0.0,
            "video_position": None,
            "midi_current": None,
            "midi_next": None,
            "is_leader": False,
        }

        # Create initial HTML file
        self._create_html_file()

        # Start update thread
        self.update_thread = threading.Thread(target=self._update_loop, daemon=True)
        self.update_thread.start()

    def _create_html_file(self):
        """Create the initial HTML file"""
        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <title>KitchenSync Debug - {self.pi_id}</title>
    <meta charset="utf-8">
    <style>
        body {{
            font-family: 'Courier New', monospace;
            background-color: #1a1a2e;
            color: #ffffff;
            margin: 20px;
            font-size: 14px;
        }}
        .header {{
            background-color: #16213e;
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 20px;
            border-left: 4px solid #0f3460;
        }}
        .section {{
            background-color: #16213e;
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 15px;
            border-left: 4px solid #0f3460;
        }}
        .highlight {{
            color: #4ecdc4;
            font-weight: bold;
        }}
        .warning {{
            color: #ff6b6b;
        }}
        .success {{
            color: #51cf66;
        }}
        .info {{
            color: #74c0fc;
        }}
        .timestamp {{
            color: #868e96;
            font-size: 12px;
        }}
        .midi-event {{
            background-color: #2d3748;
            padding: 8px;
            border-radius: 4px;
            margin: 5px 0;
        }}
        .refresh-info {{
            background-color: #2d3748;
            padding: 10px;
            border-radius: 4px;
            margin-top: 20px;
            text-align: center;
            color: #868e96;
        }}
    </style>
    <script>
        // Auto-refresh every 2 seconds
        setInterval(function() {{
            location.reload();
        }}, 2000);
    </script>
</head>
<body>
    <div class="header">
        <h1>🎬 KitchenSync Debug - {self.pi_id}</h1>
        <div class="timestamp">Last updated: <span id="timestamp">{time.strftime('%H:%M:%S')}</span></div>
    </div>

    <div class="section">
        <h2>📹 Video Status</h2>
        <div><strong>File:</strong> <span id="video-file">{self.state['video_file']}</span></div>
        <div><strong>Current Time:</strong> <span id="current-time" class="highlight">{self.state['current_time']:.1f}s</span></div>
        <div><strong>Total Time:</strong> <span id="total-time">{self.state['total_time']:.1f}s</span></div>
        <div><strong>Video Position:</strong> <span id="video-position">{self.state['video_position'] or 'N/A'}</span></div>
    </div>

    <div class="section">
        <h2>⏱️ Session Info</h2>
        <div><strong>Session Time:</strong> <span id="session-time">{self.state['session_time']:.1f}s</span></div>
        <div><strong>Leader Mode:</strong> <span id="leader-mode" class="{'success' if self.state['is_leader'] else 'info'}">{'Yes' if self.state['is_leader'] else 'No'}</span></div>
    </div>

    <div class="section">
        <h2>🎵 MIDI Events</h2>
        <div id="midi-current">
            <strong>Current:</strong> 
            <span class="{'midi-event' if self.state['midi_current'] else 'warning'}">
                {self._format_midi_event(self.state['midi_current']) if self.state['midi_current'] else 'None'}
            </span>
        </div>
        <div id="midi-next">
            <strong>Next:</strong> 
            <span class="{'midi-event' if self.state['midi_next'] else 'info'}">
                {self._format_midi_event(self.state['midi_next']) if self.state['midi_next'] else 'None'}
            </span>
        </div>
    </div>

    <div class="refresh-info">
        🔄 Auto-refreshing every 2 seconds | Manual refresh: F5
    </div>
</body>
</html>
        """

        with open(self.html_file, "w") as f:
            f.write(html_content)

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

            # Update MIDI events
            current_midi = self._format_midi_event(state["midi_current"])
            next_midi = self._format_midi_event(state["midi_next"])

            html_content = html_content.replace(
                f'id="midi-current">\n            <strong>Current:</strong> \n            <span class="{"midi-event" if state["midi_current"] else "warning"}">\n                {self._format_midi_event(state["midi_current"]) if state["midi_current"] else "None"}\n            </span>',
                f'id="midi-current">\n            <strong>Current:</strong> \n            <span class="{"midi-event" if state["midi_current"] else "warning"}">\n                {current_midi}\n            </span>',
            )
            html_content = html_content.replace(
                f'id="midi-next">\n            <strong>Next:</strong> \n            <span class="{"midi-event" if state["midi_next"] else "info"}">\n                {self._format_midi_event(state["midi_next"]) if state["midi_next"] else "None"}\n            </span>',
                f'id="midi-next">\n            <strong>Next:</strong> \n            <span class="{"midi-event" if state["midi_next"] else "info"}">\n                {next_midi}\n            </span>',
            )

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

        # Clean up HTML file
        try:
            if os.path.exists(self.html_file):
                os.remove(self.html_file)
        except Exception as e:
            log_warning(f"Could not remove HTML file: {e}", component="overlay")

        log_info("HTML overlay cleaned up", component="overlay")

    def open_in_browser(self):
        """Open the HTML file in the default browser"""
        try:
            # Open browser and then position with wmctrl
            import subprocess
            import time

            # Open chromium
            subprocess.run(
                [
                    "chromium",
                    "--new-window",
                    f"file://{self.html_file}",
                ],
                check=False,
            )

            # Wait a moment for window to appear
            time.sleep(2)

            # Use wmctrl to position and resize the window
            try:
                # Try different window title patterns
                result1 = subprocess.run(
                    ["wmctrl", "-r", "KitchenSync Debug", "-e", "0,1280,0,640,1080"],
                    check=False,
                    timeout=5,
                )
                if result1.returncode != 0:
                    # Try with chromium window
                    subprocess.run(
                        ["wmctrl", "-r", "chromium", "-e", "0,1280,0,640,1080"],
                        check=False,
                        timeout=5,
                    )
                log_info("Positioned Chrome window with wmctrl")
            except Exception as e:
                log_warning(f"Could not position Chrome window with wmctrl: {e}")

            log_info(f"HTML debug overlay opened in browser: {self.html_file}")
        except Exception as e:
            log_error(f"Failed to open HTML overlay in browser: {e}")

    def update_content(self, system_info: dict = None):
        """Update the HTML content with current system information"""
        if system_info is None:
            system_info = self._get_system_info()

        html_content = f"""<!DOCTYPE html>
<html>
<head>
    <title>KitchenSync Debug - {system_info.get('pi_id', 'Unknown')}</title>
    <meta charset="utf-8">
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; background: #1a1a1a; color: #ffffff; }}
        .header {{ background: #333; padding: 15px; border-radius: 8px; margin-bottom: 20px; }}
        .status {{ background: #2d2d2d; padding: 15px; border-radius: 8px; margin-bottom: 15px; }}
        .status.good {{ border-left: 4px solid #4CAF50; }}
        .status.warning {{ border-left: 4px solid #FF9800; }}
        .status.error {{ border-left: 4px solid #f44336; }}
        .log-section {{ background: #2d2d2d; padding: 15px; border-radius: 8px; margin-bottom: 15px; }}
        .log-content {{ background: #1a1a1a; padding: 10px; border-radius: 4px; font-family: monospace; font-size: 12px; max-height: 300px; overflow-y: auto; }}
        .refresh-info {{ text-align: center; color: #888; font-size: 12px; margin-top: 20px; }}
        .auto-refresh {{ background: #333; padding: 10px; border-radius: 4px; margin-bottom: 15px; text-align: center; }}
        .refresh-button {{ background: #4CAF50; color: white; border: none; padding: 10px 20px; border-radius: 4px; cursor: pointer; }}
        .refresh-button:hover {{ background: #45a049; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🍳 KitchenSync Debug Overlay</h1>
        <p>Pi ID: {system_info.get('pi_id', 'Unknown')} | Last Updated: {system_info.get('timestamp', 'Unknown')}</p>
    </div>

    <div class="auto-refresh">
        <button class="refresh-button" onclick="location.reload()">🔄 Manual Refresh</button>
        <p>Auto-refreshing every 5 seconds</p>
    </div>

    <div class="status {system_info.get('service_status_class', 'warning')}">
        <h2>📊 Service Status</h2>
        <p><strong>Service:</strong> {system_info.get('service_status', 'Unknown')}</p>
        <p><strong>PID:</strong> {system_info.get('service_pid', 'Unknown')}</p>
        <p><strong>Uptime:</strong> {system_info.get('service_uptime', 'Unknown')}</p>
    </div>

    <div class="status {system_info.get('vlc_status_class', 'warning')}">
        <h2>🎬 VLC Status</h2>
        <p><strong>Status:</strong> {system_info.get('vlc_status', 'Unknown')}</p>
        <p><strong>Video File:</strong> {system_info.get('video_file', 'None')}</p>
        <p><strong>VLC Process:</strong> {system_info.get('vlc_process', 'None')}</p>
    </div>

    <div class="log-section">
        <h2>📝 Recent System Log</h2>
        <div class="log-content">{system_info.get('recent_logs', 'No logs available')}</div>
    </div>

    <div class="log-section">
        <h2>🎯 Recent VLC Log</h2>
        <div class="log-content">{system_info.get('vlc_logs', 'No VLC logs available')}</div>
    </div>

    <div class="refresh-info">
        <p>This overlay automatically refreshes every 5 seconds to show real-time status</p>
        <p>Last refresh: <span id="last-refresh">{system_info.get('timestamp', 'Unknown')}</span></p>
    </div>

    <script>
        // Auto-refresh every 5 seconds
        setInterval(function() {{
            location.reload();
        }}, 5000);
        
        // Update timestamp on page load
        document.addEventListener('DOMContentLoaded', function() {{
            document.getElementById('last-refresh').textContent = new Date().toLocaleString();
        }});
    </script>
</body>
</html>"""

        try:
            with open(self.html_file, "w", encoding="utf-8") as f:
                f.write(html_content)
            log_info(f"HTML debug overlay content updated: {self.html_file}")
        except Exception as e:
            log_error(f"Failed to update HTML overlay content: {e}")

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

            # Check VLC process
            try:
                result = subprocess.run(
                    ["pgrep", "-f", "vlc"], capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    vlc_pids = result.stdout.strip().split("\n")
                    info["vlc_status"] = f'Running (PID: {", ".join(vlc_pids)})'
                    info["vlc_status_class"] = "good"
                    info["vlc_process"] = f'PIDs: {", ".join(vlc_pids)}'
                else:
                    info["vlc_status"] = "Not running"
                    info["vlc_status_class"] = "error"
            except Exception:
                info["vlc_status"] = "Check failed"
                info["vlc_status_class"] = "warning"

            # Get recent logs
            try:
                from src.core.logger import log_file_paths

                paths = log_file_paths()

                # Recent system logs
                if os.path.exists(paths["system"]):
                    with open(paths["system"], "r") as f:
                        lines = f.readlines()
                        recent = lines[-20:] if len(lines) > 20 else lines
                        info["recent_logs"] = "".join(recent)

                # Recent VLC logs
                if os.path.exists(paths["vlc_main"]):
                    with open(paths["vlc_main"], "r") as f:
                        lines = f.readlines()
                        recent = lines[-20:] if len(lines) > 20 else lines
                        info["vlc_logs"] = "".join(recent)
            except Exception:
                pass

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

    def __init__(self, pi_id: str):
        self.overlay = HTMLDebugOverlay(pi_id)
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
