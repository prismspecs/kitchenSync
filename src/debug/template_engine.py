#!/usr/bin/env python3
"""
Simple template engine for KitchenSync debug overlay
Provides basic variable substitution for HTML templates
"""

import os
import re
import shutil
from pathlib import Path
from typing import Dict, Any
from src.core.logger import log_info, log_error, log_warning


class TemplateEngine:
    """Simple template engine with variable substitution"""

    def __init__(self, template_dir: str):
        self.template_dir = Path(template_dir)
        self.template_cache = {}

    def load_template(self, template_name: str) -> str:
        """Load template from file"""
        template_path = self.template_dir / template_name

        if not template_path.exists():
            raise FileNotFoundError(f"Template not found: {template_path}")

        # Cache templates for better performance
        if template_name not in self.template_cache:
            try:
                with open(template_path, "r", encoding="utf-8") as f:
                    self.template_cache[template_name] = f.read()
                log_info(f"Loaded template: {template_name}", component="template")
            except Exception as e:
                log_error(
                    f"Error loading template {template_name}: {e}", component="template"
                )
                raise

        return self.template_cache[template_name]

    def render(self, template_name: str, context: Dict[str, Any]) -> str:
        """Render template with context variables"""
        try:
            template = self.load_template(template_name)

            # Simple variable substitution using {{variable}} syntax
            def replace_var(match):
                var_name = match.group(1).strip()
                value = context.get(var_name, f"{{MISSING: {var_name}}}")

                # Handle None values
                if value is None:
                    return "None"

                # Format numbers appropriately
                if isinstance(value, float):
                    if (
                        var_name.endswith("_time")
                        or var_name.endswith("_current_time")
                        or var_name.endswith("_total_time")
                    ):
                        return f"{value:.1f}"
                    elif var_name.endswith("_percent") or var_name.endswith(
                        "_position_percent"
                    ):
                        return f"{value:.1f}"
                    else:
                        return f"{value:.2f}"

                return str(value)

            # Replace all {{variable}} patterns
            rendered = re.sub(r"\{\{\s*([^}]+)\s*\}\}", replace_var, template)

            return rendered

        except Exception as e:
            log_error(
                f"Error rendering template {template_name}: {e}", component="template"
            )
            return f"<html><body><h1>Template Error</h1><p>{str(e)}</p></body></html>"

    def clear_cache(self):
        """Clear template cache (useful for development)"""
        self.template_cache.clear()
        log_info("Template cache cleared", component="template")


class DebugTemplateManager:
    """Manages debug overlay templates and static files"""

    def __init__(self, template_dir: str, output_dir: str = "/tmp"):
        self.template_dir = Path(template_dir)
        self.output_dir = Path(output_dir)
        self.template_engine = TemplateEngine(template_dir)

        # Ensure output directory exists
        self.output_dir.mkdir(exist_ok=True)

    def copy_static_files(self, target_dir: Path):
        """Copy static files (CSS, JS) to target directory"""
        static_src = self.template_dir / "static"
        static_dest = target_dir / "static"

        if static_src.exists():
            try:
                # Remove existing static directory if it exists
                if static_dest.exists():
                    shutil.rmtree(static_dest)

                # Copy static files
                shutil.copytree(static_src, static_dest)
                log_info(f"Copied static files to {static_dest}", component="template")

            except Exception as e:
                log_warning(f"Failed to copy static files: {e}", component="template")

    def render_debug_overlay(self, pi_id: str, system_info: Dict[str, Any]) -> str:
        """Render the debug overlay and return the output file path"""
        try:
            # Create output directory for this overlay
            overlay_dir = self.output_dir / f"kitchensync_debug_{pi_id}"
            overlay_dir.mkdir(exist_ok=True)

            # Copy static files
            self.copy_static_files(overlay_dir)

            # Prepare template context
            context = self._prepare_context(pi_id, system_info)

            # Render HTML
            html_content = self.template_engine.render("debug_overlay.html", context)

            # Write to a temporary file first
            html_file = overlay_dir / "index.html"
            tmp_file = overlay_dir / "index.html.tmp"
            with open(tmp_file, "w", encoding="utf-8") as f:
                f.write(html_content)

            # Atomically rename the file to avoid race conditions with the browser
            os.rename(tmp_file, html_file)

            log_info(f"Debug overlay rendered: {html_file}", component="template")
            return str(html_file)

        except Exception as e:
            log_error(f"Error rendering debug overlay: {e}", component="template")
            return ""

    def _prepare_context(
        self, pi_id: str, system_info: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Prepare template context from system info"""
        from datetime import datetime

        context = {
            "pi_id": pi_id,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            # Service status
            "service_status": system_info.get("service_status", "Unknown"),
            "service_status_class": system_info.get("service_status_class", "warning"),
            "service_pid": system_info.get("service_pid", "Unknown"),
            "service_uptime": system_info.get("service_uptime", "Unknown"),
            # VLC status
            "vlc_status": system_info.get("vlc_status", "Unknown"),
            "vlc_status_class": system_info.get("vlc_status_class", "warning"),
            "video_file": system_info.get("video_file", "None"),
            "video_current_time": system_info.get("video_current_time", 0.0),
            "video_total_time": system_info.get("video_total_time", 0.0),
            "video_position_percent": system_info.get("video_position", 0.0) * 100,
            "video_state": system_info.get("video_state", "unknown"),
            "video_loop_count": system_info.get("video_loop_count", 0),
            "midi_loop_count": system_info.get("midi_loop_count", 0),
            "looping_status": (
                "Enabled" if system_info.get("looping_enabled", False) else "Disabled"
            ),
            # MIDI information (removed redundant current/next, keeping comprehensive lists)
            "midi_recent_html": self._format_midi_list(
                system_info.get("midi_recent", []), "midi-recent"
            ),
            "midi_upcoming_html": self._format_midi_list(
                system_info.get("midi_upcoming", []), "midi-upcoming"
            ),
            # Logs - ensure proper HTML encoding
            "recent_logs": self._escape_html(
                system_info.get("recent_logs", "No logs available")
            ),
            "vlc_logs": self._escape_html(
                system_info.get("vlc_logs", "No VLC logs available")
            ),
        }

        return context

    def _escape_html(self, text):
        """Escape HTML characters in text"""
        if not text or text == "No logs available" or text == "No VLC logs available":
            return text

        # Basic HTML escaping
        text = str(text)
        text = text.replace("&", "&amp;")
        text = text.replace("<", "&lt;")
        text = text.replace(">", "&gt;")
        text = text.replace('"', "&quot;")
        text = text.replace("'", "&#x27;")
        return text

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

    def _format_midi_list(self, midi_list, css_class):
        """Format a list of MIDI events for HTML display"""
        if not midi_list:
            return f'<div class="midi-event {css_class}" style="opacity: 0.5;">No events</div>'

        html_items = []
        for event in midi_list[-5:]:  # Show last 5 events
            formatted = self._format_midi_event(event)
            html_items.append(f'<div class="midi-event {css_class}">{formatted}</div>')

        return "\n".join(html_items)
