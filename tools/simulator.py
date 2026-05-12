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
        self.duration = 0.0
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
            
            # Use the actual video file name from config if possible
            video_src = "/video_file"
            
            html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>KitchenSync Remote Control</title>
                <style>
                    body {{ 
                        font-family: 'Segoe UI', system-ui, sans-serif; 
                        background: #0f0f0f; 
                        color: #eee; 
                        margin: 0;
                        padding: 20px;
                        display: flex;
                        flex-direction: column;
                        align-items: center;
                    }}
                    .container {{
                        max-width: 900px;
                        width: 100%;
                        background: #1a1a1a;
                        padding: 2rem;
                        border-radius: 1rem;
                        box-shadow: 0 10px 40px rgba(0,0,0,0.6);
                        border: 1px solid #333;
                    }}
                    .video-container {{
                        width: 100%;
                        aspect-ratio: 16/9;
                        background: #000;
                        border-radius: 0.5rem;
                        overflow: hidden;
                        margin-bottom: 1.5rem;
                        border: 1px solid #444;
                    }}
                    video {{
                        width: 100%;
                        height: 100%;
                    }}
                    .header {{
                        display: flex;
                        justify-content: space-between;
                        align-items: center;
                        margin-bottom: 1.5rem;
                    }}
                    h1 {{ color: #03dac6; margin: 0; font-weight: 300; letter-spacing: 1px; font-size: 1.5rem; }}
                    .role-badge {{
                        padding: 0.3rem 0.8rem;
                        border-radius: 2rem;
                        background: #3700b3;
                        font-size: 0.8rem;
                        text-transform: uppercase;
                        font-weight: bold;
                    }}
                    .controls {{
                        display: flex;
                        gap: 1rem;
                        margin-bottom: 1.5rem;
                        align-items: center;
                    }}
                    button {{
                        background: #333;
                        color: white;
                        border: none;
                        padding: 0.6rem 1.2rem;
                        border-radius: 0.4rem;
                        cursor: pointer;
                        font-size: 1rem;
                        transition: background 0.2s;
                    }}
                    button:hover {{ background: #444; }}
                    button.primary {{ background: #03dac6; color: #000; font-weight: bold; }}
                    button.primary:hover {{ background: #04f0d9; }}
                    
                    .stats {{
                        display: grid;
                        grid-template-columns: repeat(3, 1fr);
                        gap: 1rem;
                        background: #252525;
                        padding: 1rem;
                        border-radius: 0.5rem;
                    }}
                    .stat-item {{ text-align: center; }}
                    .stat-value {{ font-size: 1.8rem; font-weight: bold; color: #bb86fc; font-variant-numeric: tabular-nums; }}
                    .stat-label {{ color: #888; font-size: 0.7rem; text-transform: uppercase; }}
                    
                    input[type=range] {{
                        flex-grow: 1;
                        accent-color: #03dac6;
                    }}
                    
                    .sync-status {{
                        margin-top: 1rem;
                        font-size: 0.9rem;
                        display: flex;
                        align-items: center;
                        gap: 0.5rem;
                    }}
                    .status-dot {{
                        height: 8px;
                        width: 8px;
                        background-color: #03dac6;
                        border-radius: 50%;
                    }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>KITCHENSYNC <span style="color: #666; font-size: 0.9rem;">REMOTE</span></h1>
                        <div id="role" class="role-badge">IDLE</div>
                    </div>

                    <div class="video-container">
                        <video id="remoteVideo" src="{video_src}" muted playsinline></video>
                    </div>

                    <div class="controls">
                        <button id="playBtn" class="primary">PLAY</button>
                        <button id="pauseBtn">PAUSE</button>
                        <input type="range" id="seekBar" min="0" max="100" value="0">
                        <span id="timeDisplay" style="font-family: monospace; min-width: 80px;">0:00 / 0:00</span>
                    </div>
                    
                    <div class="stats">
                        <div class="stat-item">
                            <div id="video_pos" class="stat-value">0.00</div>
                            <div class="stat-label">System Time</div>
                        </div>
                        <div class="stat-item">
                            <div id="drift" class="stat-value">0.000</div>
                            <div class="stat-label">Browser Drift (s)</div>
                        </div>
                        <div class="stat-item">
                            <div id="status" class="stat-value">---</div>
                            <div class="stat-label">Connection</div>
                        </div>
                    </div>

                    <div class="sync-status">
                        <span class="status-dot"></span>
                        <span>Connected to KitchenSync Cluster</span>
                    </div>
                </div>

                <script>
                    const video = document.getElementById('remoteVideo');
                    const playBtn = document.getElementById('playBtn');
                    const pauseBtn = document.getElementById('pauseBtn');
                    const seekBar = document.getElementById('seekBar');
                    const timeDisplay = document.getElementById('timeDisplay');
                    
                    let systemTime = 0;
                    let duration = 0;
                    let lastUpdate = 0;
                    let isUserSeeking = false;

                    function formatTime(seconds) {{
                        const m = Math.floor(seconds / 60);
                        const s = Math.floor(seconds % 60);
                        return `${{m}}:${{s.toString().padStart(2, '0')}}`;
                    }}

                    async function sendControl(action, value = null) {{
                        try {{
                            const url = value !== null ? `/${{action}}?value=${{value}}` : `/${{action}}`;
                            await fetch(url, {{ method: 'POST' }});
                        }} catch (e) {{
                            console.error("Control failed", e);
                        }}
                    }}

                    playBtn.onclick = () => sendControl('play');
                    pauseBtn.onclick = () => sendControl('pause');
                    
                    seekBar.oninput = () => {{
                        isUserSeeking = true;
                    }};
                    
                    seekBar.onchange = () => {{
                        const targetTime = (seekBar.value / 100) * duration;
                        sendControl('seek', targetTime);
                        isUserSeeking = false;
                    }};

                    async function update() {{
                        try {{
                            const response = await fetch('/json');
                            const data = await response.json();
                            
                            systemTime = data.video_pos;
                            duration = data.duration || 60; // Fallback
                            
                            document.getElementById('role').innerText = data.role.toUpperCase();
                            document.getElementById('video_pos').innerText = systemTime.toFixed(2);
                            document.getElementById('status').innerText = data.status.toUpperCase();
                            
                            const drift = video.currentTime - systemTime;
                            const driftEl = document.getElementById('drift');
                            driftEl.innerText = drift.toFixed(3);
                            driftEl.style.color = Math.abs(drift) > 0.1 ? '#cf6679' : '#03dac6';

                            // Sync browser video to system time
                            if (!isUserSeeking) {{
                                if (Math.abs(drift) > 0.1) {{
                                    video.currentTime = systemTime;
                                }
                                
                                if (data.status === 'Broadcasting' || data.status === 'Synced') {{
                                    if (video.paused) video.play().catch(e => {{}});
                                }} else {{
                                    if (!video.paused) video.pause();
                                }}
                                
                                seekBar.value = (systemTime / duration) * 100;
                            }}
                            
                            timeDisplay.innerText = `${{formatTime(systemTime)}} / ${{formatTime(duration)}}`;
                            
                        } catch (e) {{
                            console.error("Failed to fetch state", e);
                        }}
                    }}
                    
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
        elif self.path == "/video_file":
            # Serve the actual video file
            video_path = Path("videos/test_video.mp4")
            if not video_path.exists():
                self.send_error(404, "Video file not found")
                return
            
            self.send_response(200)
            self.send_header("Content-type", "video/mp4")
            self.send_header("Content-Length", str(video_path.stat().st_size))
            self.end_headers()
            with open(video_path, "rb") as f:
                self.wfile.write(f.read())

    def do_POST(self):
        # Handle control commands
        action = self.path.split("?")[0].strip("/")
        
        # Extract optional value
        value = None
        if "?" in self.path:
            try:
                params = self.path.split("?")[1]
                if "value=" in params:
                    value = float(params.split("value=")[1].split("&")[0])
            except:
                pass

        log(f"Remote command: {action} (value={value})")
        
        # Send UDP command to the leader
        command_manager = CommandManager()
        if action == "play":
            command_manager.send_command({"type": "remote_start"})
        elif action == "pause":
            command_manager.send_command({"type": "remote_stop"})
        elif action == "seek" and value is not None:
            command_manager.send_command({"type": "remote_seek", "value": value})
            
        self.send_response(200)
        self.end_headers()


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
    
    def on_sync(leader_time, received_at=None):
        sim_state.leader_time = leader_time
        sim_state.video_pos = player.get_position()
        sim_state.drift = sim_state.video_pos - leader_time
        sim_state.status = "Synced"
        
        # If the driver has duration, use it
        try:
            sim_state.duration = player.get_duration()
        except:
            pass

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
