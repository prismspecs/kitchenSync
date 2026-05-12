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
from networking import SyncBroadcaster, SyncReceiver, CommandManager
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
    def log_message(self, format, *args):
        return  # Quiet logs

    def do_GET(self):
        if self.path == "/":
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            html = """
            <!DOCTYPE html>
            <html>
            <head>
                <title>KitchenSync Simulator</title>
                <style>
                    body { 
                        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; 
                        background: #121212; 
                        color: #e0e0e0; 
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        height: 100vh;
                        margin: 0;
                        overflow: hidden;
                    }
                    .container {
                        background: #1e1e1e;
                        padding: 3rem;
                        border-radius: 1.5rem;
                        box-shadow: 0 10px 30px rgba(0,0,0,0.5);
                        text-align: center;
                        min-width: 400px;
                        border: 1px solid #333;
                    }
                    h1 { color: #bb86fc; margin-bottom: 2rem; font-weight: 300; letter-spacing: 2px; }
                    .stat-group { margin-bottom: 2rem; }
                    .stat-value { font-size: 3.5rem; font-weight: bold; color: #03dac6; font-variant-numeric: tabular-nums; }
                    .stat-label { color: #888; text-transform: uppercase; font-size: 0.8rem; letter-spacing: 1px; margin-top: 0.5rem; }
                    .role-badge {
                        display: inline-block;
                        padding: 0.4rem 1rem;
                        border-radius: 2rem;
                        background: #3700b3;
                        color: #fff;
                        font-size: 0.9rem;
                        margin-bottom: 2rem;
                        text-transform: uppercase;
                    }
                    .drift-indicator {
                        font-size: 1.2rem;
                        margin-top: 1rem;
                        transition: color 0.3s;
                    }
                    .status-dot {
                        height: 10px;
                        width: 10px;
                        background-color: #03dac6;
                        border-radius: 50%;
                        display: inline-block;
                        margin-right: 8px;
                        box-shadow: 0 0 10px #03dac6;
                    }
                </style>
            </head>
            <body>
                <div class="container">
                    <div id="role" class="role-badge">IDLE</div>
                    <h1>KitchenSync</h1>
                    
                    <div class="stat-group">
                        <div id="video_pos" class="stat-value">0.00</div>
                        <div class="stat-label">Video Position (Seconds)</div>
                    </div>

                    <div class="stat-group">
                        <div id="drift" class="drift-indicator">Drift: 0.000s</div>
                    </div>

                    <div style="margin-top: 2rem; color: #666; font-size: 0.9rem;">
                        <span class="status-dot"></span> <span id="status">INITIALIZING</span>
                    </div>
                </div>

                <script>
                    async function update() {
                        try {
                            const response = await fetch('/json');
                            const data = await response.json();
                            
                            document.getElementById('role').innerText = data.role.toUpperCase();
                            document.getElementById('video_pos').innerText = data.video_pos.toFixed(2);
                            document.getElementById('status').innerText = data.status.toUpperCase();
                            
                            const driftEl = document.getElementById('drift');
                            driftEl.innerText = `Drift: ${data.drift.toFixed(3)}s`;
                            
                            if (Math.abs(data.drift) > 0.1) {
                                driftEl.style.color = '#cf6679';
                            } else {
                                driftEl.style.color = '#03dac6';
                            }
                        } catch (e) {
                            console.error("Failed to fetch state", e);
                        }
                    }
                    setInterval(update, 100);
                </script>
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

def run_leader(driver_name, target_ip=None):
    sim_state.role = "leader"
    sim_state.status = "Broadcasting"
    
    player = get_video_driver(driver_name)
    player.load("dummy.mp4")
    player.play()
    
    broadcaster = SyncBroadcaster(sync_port=5005, tick_interval=0.1, broadcast_ip=target_ip)
    broadcaster.set_time_provider(player.get_position)
    broadcaster.set_duration_provider(player.get_duration)
    
    # Add CommandManager to trigger real collaborators
    command_manager = CommandManager(broadcast_ip=target_ip)
    
    log(f"Leader simulation started with '{driver_name}' driver.")
    if target_ip:
        log(f" Target IP: {target_ip} (Unicast Mode)")
    
    start_time = time.time()
    broadcaster.start_broadcasting(start_time)
    
    # Send start command to any real Pis on the network
    start_cmd = {
        "type": "start",
        "start_time": start_time,
        "schedule": [],
        "debug_mode": True
    }
    command_manager.send_command(start_cmd)
    log("Sent 'start' command to network.")
    
    last_start_send = time.time()
    
    try:
        while True:
            sim_state.video_pos = player.get_position()
            sim_state.leader_time = sim_state.video_pos
            
            # Periodically resend start command to catch late-joiners
            if time.time() - last_start_send > 2.0:
                command_manager.send_command(start_cmd)
                last_start_send = time.time()
                
            time.sleep(0.1)
    except KeyboardInterrupt:
        player.cleanup()
        broadcaster.stop_broadcasting()
        command_manager.send_command({"type": "stop"})

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
    parser.add_argument("--driver", default="mock", choices=["mock", "gst"])
    parser.add_argument("--port", type=int, default=8080, help="Web UI port")
    parser.add_argument("--target_ip", help="Explicit target IP (skips broadcast)")
    args = parser.parse_args()

    # Start Web UI in background
    threading.Thread(target=start_web_server, args=(args.port,), daemon=True).start()

    if args.mode == "leader":
        run_leader(args.driver, args.target_ip)
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
