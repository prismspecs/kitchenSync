#!/usr/bin/env python3
"""
KitchenSync Simulator & Test Harness
Cross-platform tool to simulate Leader or Collaborator nodes.
Allows testing sync logic on Desktop (Linux/macOS/Windows).
"""

import argparse
import sys
import time
import threading
import json
import socket
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from video import get_video_driver
from networking import SyncBroadcaster, SyncReceiver
from core import SyncTracker, SystemState
from core.logger import enable_system_logging

class SimulatorState:
    def __init__(self):
        self.role = "idle"
        self.video_pos = 0.0
        self.leader_time = 0.0
        self.drift = 0.0
        self.status = "Initializing"
        self.last_update = time.time()

sim_state = SimulatorState()

class StatusHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/":
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            html = f"""
            <html>
            <head>
                <title>KitchenSync Simulator - {sim_state.role.upper()}</title>
                <meta http-equiv="refresh" content="1">
                <style>
                    body {{ font-family: sans-serif; background: #222; color: #eee; text-align: center; padding-top: 50px; }}
                    .card {{ background: #333; padding: 20px; border-radius: 10px; display: inline-block; min-width: 300px; }}
                    .stat {{ font-size: 2em; color: #0f0; margin: 10px 0; }}
                    .label {{ color: #888; text-transform: uppercase; font-size: 0.8em; }}
                </style>
            </head>
            <body>
                <div class="card">
                    <h1>KitchenSync Simulator</h1>
                    <div class="label">Role</div><div>{sim_state.role.upper()}</div>
                    <div class="label">Status</div><div>{sim_state.status}</div>
                    <div class="label">Video Position</div><div class="stat">{sim_state.video_pos:.2f}s</div>
                    <div class="label">Drift</div><div class="stat" style="color: {'#f00' if abs(sim_state.drift) > 0.1 else '#0f0'}">{sim_state.drift:.3f}s</div>
                    <div class="label">Leader Time</div><div>{sim_state.leader_time:.2f}s</div>
                </div>
            </body>
            </html>
            """
            self.wfile.write(html.encode())
        elif self.path == "/json":
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(sim_state.__dict__).encode())

def start_web_server(port=8080):
    server = HTTPServer(("0.0.0.0", port), StatusHandler)
    log(f"Web UI available at http://localhost:{port}")
    server.serve_forever()

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")

def run_leader(driver_name):
    sim_state.role = "leader"
    sim_state.status = "Broadcasting"
    
    player = get_video_driver(driver_name)
    player.load("dummy.mp4")
    player.play()
    
    broadcaster = SyncBroadcaster(sync_port=5005, tick_interval=0.1)
    broadcaster.set_time_provider(player.get_position)
    broadcaster.set_duration_provider(player.get_duration)
    
    log(f"Leader simulation started with '{driver_name}' driver.")
    broadcaster.start_broadcasting(time.time())
    
    try:
        while True:
            sim_state.video_pos = player.get_position()
            sim_state.leader_time = sim_state.video_pos
            time.sleep(0.1)
    except KeyboardInterrupt:
        player.cleanup()
        broadcaster.stop_broadcasting()

def run_collaborator(driver_name):
    sim_state.role = "collaborator"
    sim_state.status = "Waiting for Sync"
    
    player = get_video_driver(driver_name)
    player.load("dummy.mp4")
    player.play()
    
    tracker = SyncTracker()
    
    def on_sync(leader_time, received_at):
        sim_state.leader_time = leader_time
        sim_state.video_pos = player.get_position()
        sim_state.drift = sim_state.video_pos - leader_time
        sim_state.status = "Synced"
        
        # Simple auto-sync logic for simulation
        if abs(sim_state.drift) > 0.3:
            log(f"Drift detected: {sim_state.drift:.3f}s. Adjusting...")
            player.seek(leader_time)

    receiver = SyncReceiver(sync_port=5005, sync_callback=on_sync)
    receiver.start_listening()
    
    log(f"Collaborator simulation started with '{driver_name}' driver.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        player.cleanup()

def main():
    # Enable system logging to see driver errors in console
    enable_system_logging(True)
    
    parser = argparse.ArgumentParser(description="KitchenSync Simulator")
    parser.add_argument("--mode", choices=["leader", "collaborator", "standalone"], required=True)
    parser.add_argument("--driver", default="mock", choices=["mock", "vlc", "gst"])
    parser.add_argument("--port", type=int, default=8080, help="Web UI port")
    args = parser.parse_args()

    # Start Web UI in background
    threading.Thread(target=start_web_server, args=(args.port,), daemon=True).start()

    if args.mode == "leader":
        run_leader(args.driver)
    elif args.mode == "collaborator":
        run_collaborator(args.driver)
    elif args.mode == "standalone":
        log(f"Standalone mode with {args.driver}...")
        player = get_video_driver(args.driver)
        player.load("test_video.mp4")
        player.play()
        try:
            while True:
                pos = player.get_position()
                print(f"\rPosition: {pos:.2f}s", end="")
                time.sleep(0.1)
        except KeyboardInterrupt:
            player.cleanup()

if __name__ == "__main__":
    main()
