#!/usr/bin/env python3
"""
HTML-based debug overlay for KitchenSync
Opens a browser window with live-updating debug information
"""

import os
import threading
import time
import webbrowser
from pathlib import Path
from typing import Optional, Dict, Any
from core.logger import log_info, log_warning, log_error


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

        # Open in browser
        try:
            webbrowser.open(f"file://{self.html_file}")
            log_info(
                f"HTML debug overlay opened in browser: {self.html_file}",
                component="overlay",
            )
        except Exception as e:
            log_warning(
                f"Could not open browser automatically: {e}", component="overlay"
            )
            log_info(
                f"Manual: open {self.html_file} in your browser", component="overlay"
            )

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


class HTMLDebugManager:
    """Manages the HTML debug overlay"""

    def __init__(self, pi_id: str, is_leader: bool = False):
        self.pi_id = pi_id
        self.is_leader = is_leader
        self.overlay = None

        try:
            self.overlay = HTMLDebugOverlay(pi_id)
            self.overlay.update_state(is_leader=is_leader)
            log_info(f"HTML debug manager created for {pi_id}", component="overlay")
        except Exception as e:
            log_error(f"Error creating HTML debug manager: {e}", component="overlay")
            self.overlay = None

    def update_debug_info(
        self,
        video_file: str,
        current_time: float,
        total_time: float,
        session_time: float,
        video_position: Optional[float],
        current_cues: list,
        upcoming_cues: list,
    ):
        """Update debug information"""
        if not self.overlay:
            return

        # Process MIDI info
        midi_current = current_cues[0] if current_cues else None
        midi_next = None

        if upcoming_cues:
            next_cue = upcoming_cues[0]
            time_until = next_cue.get("time", 0) - current_time
            midi_next = {
                "type": next_cue.get("type", "unknown"),
                "channel": next_cue.get("channel", 1),
                "time_until": time_until,
            }

        self.overlay.update_state(
            video_file=video_file,
            current_time=current_time,
            total_time=total_time,
            session_time=session_time,
            video_position=video_position,
            midi_current=midi_current,
            midi_next=midi_next,
        )

    def cleanup(self):
        """Clean up resources"""
        if self.overlay:
            self.overlay.cleanup()
            self.overlay = None
