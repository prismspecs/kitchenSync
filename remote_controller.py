#!/usr/bin/env python3
import json
import os
import shutil
import sys
import threading
import time
from dataclasses import dataclass
from http.server import HTTPServer, BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from pathlib import Path

# Add 'src' to path so internal absolute imports like 'from core.logger' work
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

# KitchenSync Imports
from src.networking.communication import CommandManager, SyncBroadcaster
from src.core.logger import log_info, enable_system_logging
from src.config.manager import ConfigManager

@dataclass
class ClusterState:
    is_playing: bool = False
    video_pos: float = 0.0
    duration: float = 0.0
    master_start_time: float = 0.0
    is_master: bool = False
    current_video: str = "test_video.mp4"

# Global state
cluster_state = ClusterState()
config = ConfigManager("leader_config.ini")
# Use config value as initial default
cluster_state.current_video = config.video_file

command_manager = CommandManager(is_leader=True)
sync_broadcaster = SyncBroadcaster(leader_id="remote-leader")

class RemoteHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/":
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            
            # Find available videos
            video_dir = Path("videos")
            available_videos = []
            if video_dir.exists():
                available_videos = [f.name for f in video_dir.glob("*") if f.suffix.lower() in [".mp4", ".mov", ".mkv", ".hevc"]]
            
            video_options = "".join([f'<option value="{v}" {"selected" if v == cluster_state.current_video else ""}>{v}</option>' for v in available_videos])

            html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>KitchenSync Remote</title>
                <meta name="viewport" content="width=device-width, initial-scale=1">
                <style>
                    body {{ font-family: sans-serif; background: #1a1a1a; color: white; display: flex; flex-direction: column; align-items: center; padding: 20px; }}
                    .card {{ background: #2a2a2a; padding: 20px; border-radius: 8px; width: 100%; max-width: 600px; box-shadow: 0 4px 6px rgba(0,0,0,0.3); margin-bottom: 20px; }}
                    .controls {{ display: flex; gap: 10px; margin-top: 20px; }}
                    button {{ padding: 10px 20px; border: none; border-radius: 4px; cursor: pointer; font-weight: bold; font-size: 16px; }}
                    .play {{ background: #2ecc71; color: white; }}
                    .stop {{ background: #e74c3c; color: white; }}
                    .status {{ margin-top: 10px; font-family: monospace; color: #aaa; }}
                    .collab-list {{ margin-top: 20px; border-top: 1px solid #444; padding-top: 10px; }}
                    .collab-item {{ display: flex; justify-content: space-between; padding: 5px 0; font-family: monospace; }}
                    .online {{ color: #2ecc71; }}
                    .video-select {{ background: #333; color: white; padding: 10px; border: 1px solid #444; border-radius: 4px; width: 100%; margin-top: 10px; }}
                    #preview {{ width: 100%; border-radius: 4px; background: black; margin-top: 15px; }}
                </style>
            </head>
            <body>
                <div class="card">
                    <h2>Cluster Control</h2>
                    
                    <label>Video File:</label>
                    <select class="video-select" id="videoSelector" onchange="changeVideo(this.value)">
                        {video_options}
                    </select>

                    <video id="preview" controls muted playsinline src="/video_file"></video>

                    <div class="controls">
                        <button class="play" onclick="post('/play')">PLAY CLUSTER</button>
                        <button class="stop" onclick="post('/stop')">STOP ALL</button>
                    </div>
                    
                    <div class="status" id="state">Status: Initializing...</div>
                </div>

                <div class="card">
                    <h3>Collaborators</h3>
                    <div id="collabs" class="collab-list"></div>
                </div>

                <script>
                    function post(path) {{
                        fetch(path, {{method: 'POST'}});
                    }}

                    function changeVideo(filename) {{
                        fetch('/set_video?file=' + encodeURIComponent(filename), {{method: 'POST'}})
                        .then(() => {{
                            document.getElementById('preview').src = '/video_file?t=' + Date.now();
                        }});
                    }}

                    function update() {{
                        fetch('/state').then(r => r.json()).then(data => {{
                            document.getElementById('state').innerHTML = 
                                `Status: ${{data.status}}<br>Time: ${{data.video_pos.toFixed(2)}}s / ${{data.duration.toFixed(2)}}s`;
                            
                            const list = document.getElementById('collabs');
                            list.innerHTML = '';
                            Object.entries(data.collaborators).forEach(([id, info]) => {{
                                list.innerHTML += `<div class="collab-item">
                                    <span>${{id}} (${{info.ip}})</span>
                                    <span class="online">${{info.status}}</span>
                                </div>`;
                            }});
                        }});
                    }}
                    setInterval(update, 1000);
                </script>
            </body>
            </html>
            """
            self.wfile.write(html.encode())
            
        elif self.path == "/state":
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            
            if not cluster_state.is_playing:
                current_status = "Stopped"
            elif not cluster_state.is_master:
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
            
        elif self.path.startswith("/video_file"):
            # Serve the currently selected video file
            video_path = Path("videos") / cluster_state.current_video
            if not video_path.exists():
                self.send_error(404, "Video file not found")
                return
            
            self.send_response(200)
            self.send_header("Content-type", "video/mp4")
            self.send_header("Content-Length", str(video_path.stat().st_size))
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()
            try:
                with open(video_path, "rb") as f:
                    shutil.copyfileobj(f, self.wfile)
            except (ConnectionResetError, BrokenPipeError):
                pass
            except Exception as e:
                log_info(f"Stream error: {e}", component="remote")
        else:
            self.send_error(404)

    def do_POST(self):
        parsed_path = urlparse(self.path)
        action = parsed_path.path.strip("/")
        query = parse_qs(parsed_path.query)
        
        if action == "play":
            cluster_state.is_playing = True
            cluster_state.is_master = True
            cluster_state.master_start_time = time.time()
            
            # Send immediate start command with the SELECTED file
            start_cmd = {
                "type": "start",
                "video_file": cluster_state.current_video,
                "start_time": cluster_state.master_start_time,
                "schedule": [],
                "debug_mode": True
            }
            command_manager.send_command(start_cmd)
            log_info(f"Cluster PLAY: {cluster_state.current_video}", component="remote")
            
        elif action == "stop":
            cluster_state.is_playing = False
            cluster_state.is_master = False
            command_manager.send_command({"type": "stop"})
            log_info("Cluster STOP", component="remote")

        elif action == "set_video":
            new_file = query.get("file", [None])[0]
            if new_file:
                cluster_state.current_video = new_file
                log_info(f"Video changed to: {new_file}", component="remote")
                # If currently playing, we should probably stop the old one
                if cluster_state.is_playing:
                    command_manager.send_command({"type": "stop"})
                    cluster_state.is_playing = False
            
        self.send_response(204)
        self.end_headers()

class RobustRemoteServer(ThreadingHTTPServer):
    def handle_error(self, request, client_address):
        import sys
        exctype, value = sys.exc_info()[:2]
        if exctype in (ConnectionResetError, BrokenPipeError):
            return
        super().handle_error(request, client_address)

def start_remote():
    """Start the remote controller services"""
    enable_system_logging(True)
    
    # Master Clock Thread (only active when is_master is True)
    def master_clock():
        last_broadcast = 0
        while True:
            if cluster_state.is_master and cluster_state.is_playing:
                cluster_state.video_pos = time.time() - cluster_state.master_start_time
                
                # Periodically re-send start command
                if time.time() - last_broadcast > 2.0:
                    start_cmd = {
                        "type": "start",
                        "video_file": cluster_state.current_video,
                        "start_time": cluster_state.master_start_time,
                        "schedule": [],
                        "debug_mode": True
                    }
                    command_manager.send_command(start_cmd)
                    last_broadcast = time.time()
                
                # Broadcast actual time sync
                sync_broadcaster.broadcast_sync(cluster_state.video_pos)
                    
            time.sleep(0.05)
    
    threading.Thread(target=master_clock, daemon=True).start()
    
    # Start networking
    command_manager.start_listening()
    
    # Start web server
    web_thread = threading.Thread(
        target=lambda: RobustRemoteServer(("0.0.0.0", 8080), RemoteHandler).serve_forever(),
        daemon=True
    )
    web_thread.start()
    log_info("Remote Controller Web UI available at http://localhost:8080", component="remote")
    log_info(f"Default video from config: {cluster_state.current_video}", component="remote")

if __name__ == "__main__":
    try:
        start_remote()
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        log_info("Shutting down remote controller...")
