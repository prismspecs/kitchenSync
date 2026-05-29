#!/usr/bin/env python3
"""
Native Tkinter-based debug overlay for kSync.
Runs as a decoupled standalone subprocess to prevent multi-threaded X11 conflicts with GStreamer.
"""

import tkinter as tk
import json
import os
import sys
import threading
import time
import subprocess
import argparse
from typing import Optional
from pathlib import Path

# Ensure src/ is in the Python path for imports
script_dir = Path(__file__).resolve().parent
if str(script_dir.parent) not in sys.path:
    sys.path.insert(0, str(script_dir.parent))

try:
    from core.logger import log_info, log_error, log_warning
except ImportError:
    # Standalone mode fallback if imports fail
    def log_info(msg, component="overlay"): print(f"[INFO] [{component}] {msg}")
    def log_error(msg, component="overlay"): print(f"[ERROR] [{component}] {msg}", file=sys.stderr)
    def log_warning(msg, component="overlay"): print(f"[WARNING] [{component}] {msg}")


class NativeDebugOverlay:
    """
    Manages the standalone debug overlay subprocess.
    Writes telemetry data to RAM-backed file `/dev/shm/ksync_overlay.json` at 5Hz.
    """

    def __init__(self, node_instance, role: str = "collaborator"):
        self.node = node_instance
        self.device_id = node_instance.config.device_id
        self.video_player = node_instance.video_player
        self.role = role
        self.running = False
        self.process: Optional[subprocess.Popen] = None
        self.update_thread: Optional[threading.Thread] = None

    def start(self):
        """Start the status writer thread and spawn the overlay subprocess."""
        if self.running:
            return

        if not os.environ.get("DISPLAY"):
            log_warning("Native debug overlay: No DISPLAY found, skipping GUI launch.", component="overlay")
            return
            
        self.running = True
        
        # 1. Start background thread to write telemetry status
        self.update_thread = threading.Thread(target=self._write_status_loop, daemon=True)
        self.update_thread.start()
        
        # 2. Spawn standalone Tkinter GUI as a separate process
        try:
            script_path = os.path.abspath(__file__)
            env = os.environ.copy()
            self.process = subprocess.Popen(
                [sys.executable, script_path, "--role", self.role, "--device-id", self.device_id],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            log_info(f"Native debug overlay subprocess started with PID {self.process.pid} (Role: {self.role})", component="overlay")
        except Exception as e:
            log_error(f"Failed to spawn native overlay subprocess: {e}", component="overlay")
            self.running = False

    def _write_status_loop(self):
        """Periodically write status telemetry to /dev/shm/ksync_overlay.json."""
        status_path = "/dev/shm/ksync_overlay.json"
        
        while self.running:
            try:
                data = {
                    "device_id": self.device_id,
                    "role": self.role,
                    "state": "stopped",
                    "position": 0.0,
                    "duration": 0.0,
                    "decoder": "unknown",
                    "video_sink": "unknown",
                    "sync_dev_ms": 0.0,
                    "speed": 1.0000,
                    "clients": 0
                }
                
                if self.video_player:
                    info = self.video_player.get_info()
                    data["position"] = info.get("position", 0.0) or 0.0
                    data["duration"] = info.get("duration", 0.0) or 0.0
                    data["state"] = info.get("state", "stopped") or "stopped"
                    data["decoder"] = info.get("decoder", "unknown") or "unknown"
                    data["video_sink"] = info.get("video_sink", "unknown") or "unknown"
                
                if self.role == "collaborator":
                    dev = 0.0
                    if getattr(self.node, "deviation_samples", None):
                        dev = self.node.deviation_samples[-1]
                    data["sync_dev_ms"] = dev * 1000.0
                    data["speed"] = getattr(self.video_player, "current_rate", 1.0)
                else:
                    # Leader
                    clients = len(self.node.command_manager.get_collaborators())
                    data["clients"] = clients
                    
                # Write to temp file first then rename atomically
                temp_path = status_path + ".tmp"
                with open(temp_path, "w") as f:
                    json.dump(data, f)
                os.rename(temp_path, status_path)
            except Exception:
                pass
            time.sleep(0.2)

    def stop(self):
        """Stop the status updater and terminate the subprocess."""
        self.running = False
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=1.0)
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass
            self.process = None
            
        # Cleanup status file
        try:
            status_path = "/dev/shm/ksync_overlay.json"
            if os.path.exists(status_path):
                os.remove(status_path)
        except Exception:
            pass
            
        log_info("Native debug overlay stopped", component="overlay")


def run_standalone_gui(role: str, device_id: str):
    """Standalone Tkinter UI loop running on the main thread of the subprocess."""
    try:
        root = tk.Tk()
        root.title(f"KS Debug: {device_id}")
        
        # Styling
        bg_color = "#12121a"
        fg_color = "#ffffff"
        root.configure(bg=bg_color)
        
        # Position: Top Right
        width = 280
        height = 150 if role == "leader" else 190
        
        screen_width = root.winfo_screenwidth()
        if screen_width <= 0:
            screen_width = 1920
            
        x = screen_width - width - 20
        y = 20
        root.geometry(f"{width}x{height}+{x}+{y}")
        
        # X11 Window Manager hints to keep it topmost and bypass focus
        root.attributes('-alpha', 0.85)
        root.attributes('-topmost', True)
        
        # CRITICAL: overrideredirect(True) bypasses the window manager completely.
        # This prevents the fullscreen GStreamer window from swallowing or hiding our overlay!
        root.overrideredirect(True)
        
        # Widgets
        tk.Label(
            root, 
            text=f"kSync Node: {device_id}", 
            font=("monospace", 10, "bold"), 
            fg="#00d2ff", 
            bg=bg_color
        ).pack(anchor="w", padx=15, pady=(10, 5))
        
        label_role = tk.Label(
            root, 
            text=f"Role: {role.upper()}", 
            font=("monospace", 9), 
            fg="#aaaaaa", 
            bg=bg_color
        )
        label_role.pack(anchor="w", padx=15)
        
        label_status = tk.Label(
            root, 
            text="State: STOPPED", 
            font=("monospace", 9), 
            fg=fg_color, 
            bg=bg_color
        )
        label_status.pack(anchor="w", padx=15)
        
        label_time = tk.Label(
            root, 
            text="Time: 0.00 / 0.00s", 
            font=("monospace", 9), 
            fg=fg_color, 
            bg=bg_color
        )
        label_time.pack(anchor="w", padx=15)
        
        if role == "collaborator":
            label_sync = tk.Label(
                root, 
                text="Sync Dev: +0.0ms", 
                font=("monospace", 9, "bold"), 
                fg="#00ff00", 
                bg=bg_color
            )
            label_sync.pack(anchor="w", padx=15)
            
            label_speed = tk.Label(
                root, 
                text="Speed: 1.0000x", 
                font=("monospace", 9), 
                fg=fg_color, 
                bg=bg_color
            )
            label_speed.pack(anchor="w", padx=15)
            
            label_clients = None
        else:
            label_sync = None
            label_speed = None
            label_clients = tk.Label(
                root, 
                text="Clients: 0 connected", 
                font=("monospace", 9), 
                fg=fg_color, 
                bg=bg_color
            )
            label_clients.pack(anchor="w", padx=15)

        label_decoder = tk.Label(
            root, 
            text="Decoder: Unknown", 
            font=("monospace", 8), 
            fg="#777777", 
            bg=bg_color
        )
        label_decoder.pack(anchor="w", padx=15, pady=(5, 10))

        status_path = "/dev/shm/ksync_overlay.json"

        def update_gui():
            try:
                if os.path.exists(status_path):
                    with open(status_path, "r") as f:
                        data = json.load(f)
                    
                    pos = data.get("position", 0.0)
                    dur = data.get("duration", 0.0)
                    state = data.get("state", "stopped")
                    decoder = data.get("decoder", "unknown")
                    sink = data.get("video_sink", "unknown")
                    
                    label_time.config(text=f"Time: {pos:.2f} / {dur:.2f}s")
                    label_status.config(text=f"State: {state.upper()}")
                    label_decoder.config(text=f"Decoder: {decoder} ({sink})")
                    
                    if role == "collaborator":
                        dev = data.get("sync_dev_ms", 0.0)
                        label_sync.config(text=f"Sync Dev: {dev:+.1f}ms")
                        
                        speed = data.get("speed", 1.0)
                        label_speed.config(text=f"Speed: {speed:.4f}x")
                    else:
                        clients = data.get("clients", 0)
                        label_clients.config(text=f"Clients: {clients} connected")
            except Exception:
                pass
                
            # Poll status file every 200ms
            root.after(200, update_gui)

        update_gui()
        root.mainloop()
    except Exception as e:
        sys.stderr.write(f"Standalone overlay error: {e}\n")
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="kSync Debug Overlay Subprocess")
    parser.add_argument("--role", default="collaborator")
    parser.add_argument("--device-id", default="unknown")
    args = parser.parse_args()
    
    # Run the GUI on the main thread of the subprocess
    run_standalone_gui(args.role, args.device_id)
