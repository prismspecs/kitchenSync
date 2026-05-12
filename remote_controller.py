#!/usr/bin/env python3
"""
KitchenSync Remote Controller
A web-based interface for controlling the KitchenSync cluster.
Allows real-time playback control, cluster monitoring, and synchronized video preview.
"""

import argparse
import sys
import time
import threading
import json
import socket
import shutil
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from networking.communication import SyncReceiver, CommandManager, SyncBroadcaster
from core.logger import log_info, enable_system_logging

class ClusterState:
    def __init__(self):
        self.video_pos = 0.0
        self.duration = 100.0 # Default until known
        self.leader_time = 0.0
        self.status = "Disconnected"
        self.collaborators = {}
        self.last_sync = 0
        self.is_playing = False
        self.is_master = False
        self.master_start_time = 0

cluster_state = ClusterState()
command_manager = CommandManager()
broadcaster = SyncBroadcaster()

class RemoteHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return  # Quiet logs

    def do_GET(self):
        if self.path == "/":
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(self._get_html_template().encode())
        elif self.path == "/json":
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            
            # Auto-disconnect if sync lost
            current_status = cluster_state.status
            if not cluster_state.is_master and time.time() - cluster_state.last_sync > 5:
                current_status = "Disconnected"
            elif cluster_state.is_master:
                current_status = "Leading"

            state_data = {
                "video_pos": cluster_state.video_pos,
                "duration": cluster_state.duration,
                "status": current_status,
                "collaborators": command_manager.get_collaborators(),
                "is_playing": cluster_state.is_playing,
                "is_master": cluster_state.is_master
            }
            self.wfile.write(json.dumps(state_data).encode())
        elif self.path == "/video_file":
            # Serve the actual video file
            video_path = Path("videos/test_video.mp4")
            if not video_path.exists():
                self.send_error(404, "Video file not found")
                return
            
            self.send_response(200)
            self.send_header("Content-type", "video/mp4")
            self.send_header("Content-Length", str(video_path.stat().st_size))
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()
            with open(video_path, "rb") as f:
                shutil.copyfileobj(f, self.wfile)
        else:
            self.send_error(404)

    def do_POST(self):
        parsed_path = urlparse(self.path)
        action = parsed_path.path.strip("/")
        query = parse_qs(parsed_path.query)
        
        value = query.get("value", [None])[0]
        if value:
            try:
                value = float(value)
            except ValueError:
                value = None

        log_info(f"Remote command: {action} (value={value})", component="remote")
        
        if action == "play":
            # If we haven't heard from a leader in a while, we become the leader
            if time.time() - cluster_state.last_sync > 2.0:
                cluster_state.is_master = True
                cluster_state.is_playing = True
                cluster_state.master_start_time = time.time() - cluster_state.video_pos
                broadcaster.start_broadcasting(cluster_state.master_start_time)
                log_info("Remote taking over as Cluster Leader", component="remote")
            
            command_manager.send_command({"type": "remote_start"})
            cluster_state.is_playing = True
            
        elif action == "pause":
            if cluster_state.is_master:
                cluster_state.is_playing = False
                broadcaster.stop_broadcasting()
                
            command_manager.send_command({"type": "remote_stop"})
            cluster_state.is_playing = False
            
        elif action == "seek" and value is not None:
            if cluster_state.is_master:
                cluster_state.video_pos = value
                cluster_state.master_start_time = time.time() - value
                
            command_manager.send_command({"type": "remote_seek", "value": value})
            
        self.send_response(200)
        self.end_headers()

    def _get_html_template(self):
        video_src = "/video_file"
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>KitchenSync Remote Controller</title>
            <style>
                :root {{
                    --bg: #0a0a0b;
                    --card: #151518;
                    --primary: #00f5d4;
                    --secondary: #9b5de5;
                    --text: #e0e0e6;
                    --text-muted: #888;
                    --accent: #f15bb5;
                    --danger: #fee440;
                }}
                body {{ 
                    font-family: 'Inter', -apple-system, system-ui, sans-serif; 
                    background: var(--bg); 
                    color: var(--text); 
                    margin: 0;
                    padding: 20px;
                    display: flex;
                    flex-direction: column;
                    align-items: center;
                }}
                .container {{
                    max-width: 1000px;
                    width: 100%;
                }}
                .card {{
                    background: var(--card);
                    padding: 2rem;
                    border-radius: 1rem;
                    box-shadow: 0 20px 50px rgba(0,0,0,0.5);
                    border: 1px solid #222;
                    margin-bottom: 2rem;
                }}
                .video-section {{
                    position: relative;
                    width: 100%;
                    aspect-ratio: 16/9;
                    background: #000;
                    border-radius: 0.8rem;
                    overflow: hidden;
                    border: 1px solid #333;
                    margin-bottom: 1.5rem;
                }}
                video {{
                    width: 100%;
                    height: 100%;
                    object-fit: contain;
                }}
                .overlay-controls {{
                    position: absolute;
                    bottom: 0;
                    left: 0;
                    right: 0;
                    background: linear-gradient(transparent, rgba(0,0,0,0.8));
                    padding: 20px;
                    display: flex;
                    align-items: center;
                    gap: 15px;
                    opacity: 0;
                    transition: opacity 0.3s;
                }}
                .video-section:hover .overlay-controls {{ opacity: 1; }}
                
                .header {{
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    margin-bottom: 2rem;
                }}
                h1 {{ 
                    margin: 0; 
                    font-size: 1.5rem; 
                    font-weight: 700; 
                    letter-spacing: -0.5px;
                    display: flex;
                    align-items: center;
                    gap: 10px;
                }}
                h1 span {{ color: var(--primary); }}
                
                .status-badge {{
                    padding: 4px 12px;
                    border-radius: 20px;
                    font-size: 0.75rem;
                    font-weight: 600;
                    text-transform: uppercase;
                    background: #222;
                    color: var(--text-muted);
                }}
                .status-connected {{ background: rgba(0, 245, 212, 0.1); color: var(--primary); }}
                .status-master {{ background: var(--secondary); color: #fff; }}

                .main-controls {{
                    display: flex;
                    gap: 12px;
                    align-items: center;
                    margin-bottom: 2rem;
                }}
                button {{
                    background: #222;
                    color: white;
                    border: 1px solid #333;
                    padding: 10px 24px;
                    border-radius: 8px;
                    cursor: pointer;
                    font-weight: 600;
                    transition: all 0.2s;
                }}
                button:hover {{ background: #2a2a2e; border-color: #444; }}
                button.btn-primary {{ 
                    background: var(--primary); 
                    color: #000; 
                    border: none;
                }}
                button.btn-primary:hover {{ background: #00d9bc; transform: translateY(-1px); }}
                
                input[type=range] {{
                    flex-grow: 1;
                    accent-color: var(--primary);
                    cursor: pointer;
                }}
                
                .grid {{
                    display: grid;
                    grid-template-columns: 1fr 1fr 1fr;
                    gap: 20px;
                }}
                .stat-card {{
                    background: #1a1a1e;
                    padding: 15px;
                    border-radius: 12px;
                    text-align: center;
                }}
                .stat-value {{ font-size: 1.5rem; font-weight: 700; color: var(--secondary); margin-bottom: 4px; }}
                .stat-label {{ font-size: 0.7rem; text-transform: uppercase; color: var(--text-muted); font-weight: 600; }}

                .collaborators-list {{
                    margin-top: 2rem;
                }}
                .collaborator-item {{
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    padding: 12px 16px;
                    background: #1a1a1e;
                    border-radius: 10px;
                    margin-bottom: 8px;
                    border-left: 3px solid #333;
                }}
                .collaborator-item.online {{ border-left-color: var(--primary); }}
                .pi-info {{ display: flex; flex-direction: column; }}
                .pi-name {{ font-weight: 600; font-size: 0.9rem; }}
                .pi-ip {{ font-size: 0.75rem; color: var(--text-muted); }}
                .pi-status {{ font-size: 0.7rem; font-weight: 700; color: var(--primary); }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>KITCHEN<span>SYNC</span> REMOTE</h1>
                    <div id="connectionStatus" class="status-badge">DISCONNECTED</div>
                </div>

                <div class="card">
                    <div class="video-section">
                        <video id="remoteVideo" src="{video_src}" muted playsinline></video>
                        <div class="overlay-controls">
                            <span id="overlayTime" style="font-family: monospace;">0:00</span>
                        </div>
                    </div>

                    <div class="main-controls">
                        <button id="playBtn" class="btn-primary">PLAY CLUSTER</button>
                        <button id="pauseBtn">PAUSE ALL</button>
                        <input type="range" id="seekBar" min="0" max="100" value="0">
                        <span id="timeDisplay" style="font-family: monospace; font-size: 0.9rem; min-width: 90px; text-align: right;">0:00 / 0:00</span>
                    </div>

                    <div class="grid">
                        <div class="stat-card">
                            <div id="video_pos" class="stat-value">0.00</div>
                            <div class="stat-label">System Time</div>
                        </div>
                        <div class="stat-card">
                            <div id="sync_drift" class="stat-value">0.000</div>
                            <div class="stat-label">Browser Sync (s)</div>
                        </div>
                        <div class="stat-card">
                            <div id="pi_count" class="stat-value">0</div>
                            <div class="stat-label">Active Nodes</div>
                        </div>
                    </div>
                </div>

                <div class="card collaborators-list">
                    <h2 style="font-size: 1rem; margin-top: 0; color: var(--text-muted); text-transform: uppercase; letter-spacing: 1px;">Cluster Nodes</h2>
                    <div id="piList">
                        <div style="color: var(--text-muted); font-size: 0.9rem; padding: 20px; text-align: center;">Scanning for Pi nodes...</div>
                    </div>
                </div>
            </div>

            <script>
                const video = document.getElementById('remoteVideo');
                const playBtn = document.getElementById('playBtn');
                const pauseBtn = document.getElementById('pauseBtn');
                const seekBar = document.getElementById('seekBar');
                const timeDisplay = document.getElementById('timeDisplay');
                const overlayTime = document.getElementById('overlayTime');
                
                let isUserSeeking = false;
                let duration = 0;

                function formatTime(seconds) {{
                    if (isNaN(seconds)) return "0:00";
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
                
                seekBar.oninput = () => {{ isUserSeeking = true; }};
                seekBar.onchange = () => {{
                    const targetTime = (seekBar.value / 100) * duration;
                    sendControl('seek', targetTime);
                    isUserSeeking = false;
                }};

                async function update() {{
                    try {{
                        const response = await fetch('/json');
                        const data = await response.json();
                        
                        const systemTime = data.video_pos;
                        duration = data.duration || video.duration || 0;
                        
                        document.getElementById('connectionStatus').innerText = data.status;
                        document.getElementById('connectionStatus').className = "status-badge " + 
                            (data.is_master ? 'status-master' : (data.status === 'Connected' ? 'status-connected' : ''));
                        
                        document.getElementById('video_pos').innerText = systemTime.toFixed(2);
                        
                        const drift = video.currentTime - systemTime;
                        const driftEl = document.getElementById('sync_drift');
                        driftEl.innerText = Math.abs(drift).toFixed(3);
                        driftEl.style.color = Math.abs(drift) > 0.15 ? 'var(--accent)' : 'var(--primary)';

                        // Browser Sync Logic
                        if (!isUserSeeking) {{
                            if (Math.abs(drift) > 0.15) {{
                                video.currentTime = systemTime;
                            }}
                            
                            if (data.is_playing) {{
                                if (video.paused) video.play().catch(e => {{}});
                            }} else {{
                                if (!video.paused) video.pause();
                            }}
                            
                            if (duration > 0) {{
                                seekBar.value = (systemTime / duration) * 100;
                            }}
                        }}
                        
                        timeDisplay.innerText = `${{formatTime(systemTime)}} / ${{formatTime(duration)}}`;
                        overlayTime.innerText = formatTime(systemTime);

                        // Collaborator List
                        const collaborators = data.collaborators || {{}};
                        const piList = document.getElementById('piList');
                        const piCount = Object.keys(collaborators).length;
                        document.getElementById('pi_count').innerText = piCount;

                        if (piCount === 0) {{
                            piList.innerHTML = '<div style="color: var(--text-muted); font-size: 0.9rem; padding: 20px; text-align: center;">No nodes detected on network.</div>';
                        }} else {{
                            piList.innerHTML = Object.entries(collaborators).map(([id, info]) => `
                                <div class="collaborator-item ${{info.online ? 'online' : ''}}">
                                    <div class="pi-info">
                                        <div class="pi-name">${{id}}</div>
                                        <div class="pi-ip">${{info.ip}}</div>
                                    </div>
                                    <div class="pi-status">${{info.online ? 'ONLINE' : 'OFFLINE'}}</div>
                                </div>
                            `).join('');
                        }}
                        
                    }} catch (e) {{
                        console.error("Update loop failed", e);
                    }}
                }}
                
                setInterval(update, 200);
            </script>
        </body>
        </html>
        """

def start_remote():
    """Start the remote controller services"""
    enable_system_logging(True)
    
    # Master Clock Thread (only active when is_master is True)
    def master_clock():
        while True:
            if cluster_state.is_master and cluster_state.is_playing:
                cluster_state.video_pos = time.time() - cluster_state.master_start_time
            time.sleep(0.05)
    
    threading.Thread(target=master_clock, daemon=True).start()
    
    # Start web server
    web_thread = threading.Thread(
        target=lambda: ThreadingHTTPServer(("0.0.0.0", 8080), RemoteHandler).serve_forever(),
        daemon=True
    )
    web_thread.start()
    log_info("Remote Controller Web UI available at http://localhost:8080", component="remote")

    # Start Sync Listening (to mirror the cluster state in the UI)
    def on_sync(leader_time, received_at):
        # If we hear a real leader, we stop being the master to avoid collisions
        if cluster_state.is_master:
            cluster_state.is_master = False
            broadcaster.stop_broadcasting()
            log_info("Hardware Leader detected. Remote stepping down as Master.", component="remote")

        cluster_state.leader_time = leader_time
        cluster_state.video_pos = leader_time
        cluster_state.last_sync = time.time()
        cluster_state.status = "Connected"
        cluster_state.is_playing = True
        
    sync_receiver = SyncReceiver(sync_port=5005, sync_callback=on_sync)
    sync_receiver.start_listening()
    
    # Configure broadcaster
    broadcaster.set_time_provider(lambda: cluster_state.video_pos)
    
    # Start Command Listening (to track Pi registrations)
    command_manager.start_listening()
    
    log_info("Remote Controller active. Monitoring cluster sync...", component="remote")
    
    try:
        while True:
            # Keep main thread alive
            time.sleep(1)
    except KeyboardInterrupt:
        log_info("Shutting down Remote Controller", component="remote")
        sync_receiver.stop_listening()
        command_manager.stop_listening()

if __name__ == "__main__":
    start_remote()
