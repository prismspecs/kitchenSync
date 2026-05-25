#!/usr/bin/env python3
"""
Native Tkinter-based debug overlay for kSync
Provides a lightweight alternative to the browser-based overlay.
"""

import tkinter as tk
import threading
import time
import os
from typing import Optional, Dict, Any
from core.logger import log_info, log_error, log_warning

class NativeDebugOverlay:
    """
    Lightweight Tkinter overlay that shows live sync status.
    Designed to run on Collaborator nodes to avoid Firefox overhead.
    """

    def __init__(self, device_id: str, video_player=None, midi_scheduler=None):
        self.device_id = device_id
        self.video_player = video_player
        self.midi_scheduler = midi_scheduler
        self.running = False
        self.root = None
        self.update_thread = None
        self.state = {
            "position": 0.0,
            "duration": 0.0,
            "state": "unknown",
            "hw_accel": False,
            "sink": "unknown",
            "decoder": "unknown",
            "midi_loop": 0
        }

    def start(self):
        """Start the overlay in a background thread."""
        if self.running:
            return

        if not os.environ.get("DISPLAY"):
            log_warning("Native debug overlay: No DISPLAY found, skipping GUI launch.", component="overlay")
            return
            
        self.running = True
        self.update_thread = threading.Thread(target=self._run_gui, daemon=True)
        self.update_thread.start()
        log_info(f"Native debug overlay started for {self.device_id}", component="overlay")

    def _run_gui(self):
        """GUI Main Loop."""
        try:
            self.root = tk.Tk()
            self.root.title(f"KS Debug: {self.device_id}")
            
            # Styling
            bg_color = "#1a1a2e"
            fg_color = "#ffffff"
            self.root.configure(bg=bg_color)
            
            # Position: Top Right
            width = 300
            height = 200
            screen_width = self.root.winfo_screenwidth()
            # Try to get screen width from xrandr if it returns 0 (some headless setups)
            if screen_width <= 0:
                screen_width = 1920
                
            x = screen_width - width - 20
            y = 20
            self.root.geometry(f"{width}x{height}+{x}+{y}")
            
            # Semi-transparency (X11)
            self.root.attributes('-alpha', 0.85)
            self.root.attributes('-topmost', True)
            
            # Widgets
            tk.Label(self.root, text=f"KITCHENSYNC DEBUG", font=("monospace", 12, "bold"), fg="#4a90e2", bg=bg_color).pack(pady=5)
            
            self.label_id = tk.Label(self.root, text=f"ID: {self.device_id}", font=("monospace", 10), fg=fg_color, bg=bg_color)
            self.label_id.pack(anchor="w", padx=15)
            
            self.label_time = tk.Label(self.root, text="Time: 0.0 / 0.0s", font=("monospace", 10), fg=fg_color, bg=bg_color)
            self.label_time.pack(anchor="w", padx=15)
            
            self.label_status = tk.Label(self.root, text="State: Stopped", font=("monospace", 10), fg=fg_color, bg=bg_color)
            self.label_status.pack(anchor="w", padx=15)
            
            self.label_hw = tk.Label(self.root, text="HW Accel: Unknown", font=("monospace", 10), fg=fg_color, bg=bg_color)
            self.label_hw.pack(anchor="w", padx=15)
            
            self.label_sink = tk.Label(self.root, text="Sink: Unknown", font=("monospace", 8), fg="#aaaaaa", bg=bg_color)
            self.label_sink.pack(anchor="w", padx=15)

            self.label_midi = tk.Label(self.root, text="MIDI Loop: 0", font=("monospace", 10), fg="#ccff00", bg=bg_color)
            self.label_midi.pack(anchor="w", padx=15)

            self._update_loop()
            self.root.mainloop()
        except Exception as e:
            log_error(f"Native overlay GUI error: {e}", component="overlay")
            self.running = False

    def _update_loop(self):
        """Update widgets from player/scheduler state."""
        if not self.running or not self.root:
            return

        try:
            if self.video_player:
                info = self.video_player.get_info()
                pos = info.get("position", 0.0)
                dur = info.get("duration", 0.0)
                state = info.get("state", "unknown")
                is_hw = info.get("is_hardware_accelerated", False)
                sink = info.get("video_sink", "unknown")
                
                self.label_time.config(text=f"Time: {pos:.1f} / {dur:.1f}s")
                self.label_status.config(text=f"State: {state.upper()}")
                
                hw_text = "ACTIVE" if is_hw else "INACTIVE"
                hw_color = "#00ff00" if is_hw else "#ff9900"
                self.label_hw.config(text=f"HW Accel: {hw_text}", fg=hw_color)
                self.label_sink.config(text=f"Sink: {sink}")

            if self.midi_scheduler:
                stats = self.midi_scheduler.get_stats()
                loop = stats.get("loop_count", 0)
                self.label_midi.config(text=f"MIDI Loop: #{loop}")

        except Exception as e:
            pass

        # Poll every 500ms for responsiveness without too much CPU
        if self.running:
            self.root.after(500, self._update_loop)

    def stop(self):
        """Stop the overlay and cleanup GUI."""
        self.running = False
        if self.root:
            try:
                self.root.quit()
                self.root.destroy()
            except:
                pass
        log_info("Native debug overlay stopped", component="overlay")

class NativeDebugManager:
    """Manages the Native Tkinter debug overlay (Compatibility wrapper)"""

    def __init__(self, device_id: str, video_player=None, midi_scheduler=None):
        self.overlay = NativeDebugOverlay(device_id, video_player, midi_scheduler)

    def start(self):
        self.overlay.start()

    def stop(self):
        self.overlay.stop()

    def update_debug_info(self, **kwargs):
        # The native overlay polls the player directly, 
        # but we can accept updates if needed for consistency
        pass

    def cleanup(self):
        self.stop()
