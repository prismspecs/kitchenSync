#!/usr/bin/env python3
import json
import os
import sys
import threading
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import parse_qs, urlparse
import socket

# Add parent directory to path to allow importing from src
sys.path.append(str(Path(__file__).resolve().parent.parent))

from config.manager import ConfigManager
from core.logger import enable_system_logging, log_info, log_warning
from networking.communication import CommandManager, SyncBroadcaster
from video.file_manager import VideoFileManager


@dataclass
class ClusterState:
    is_playing: bool = False
    video_pos: float = 0.0
    duration: float = 0.0
    master_start_time: float = 0.0
    is_master: bool = False
    current_video: str = ""


LOCAL_LEADER_ID = "remote-leader"

cluster_state = ClusterState()
config = ConfigManager("leader_config.ini")
video_manager = VideoFileManager(config.video_file, config.usb_mount_point)
command_manager = CommandManager()
sync_broadcaster = SyncBroadcaster()
sync_broadcaster.leader_id = LOCAL_LEADER_ID

config_snapshots: Dict[str, Dict[str, Any]] = {}
config_messages: Dict[str, Dict[str, Any]] = {}

# Media state cache
media_snapshots: Dict[str, List[Dict[str, Any]]] = {}


TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"


def resolve_byte_range(range_header: str | None, file_size: int) -> tuple[int, int] | None:
    if not range_header:
        return None
    if file_size <= 0 or not range_header.startswith("bytes="):
        raise ValueError("Invalid range header")

    raw_range = range_header[6:].split(",", 1)[0].strip()
    start_text, separator, end_text = raw_range.partition("-")
    if separator != "-":
        raise ValueError("Invalid range header")

    if start_text == "":
        suffix_length = int(end_text)
        if suffix_length <= 0:
            raise ValueError("Invalid suffix range")
        if suffix_length >= file_size:
            return (0, file_size - 1)
        return (file_size - suffix_length, file_size - 1)

    start = int(start_text)
    end = file_size - 1 if end_text == "" else int(end_text)

    if start < 0 or start >= file_size or end < start:
        raise ValueError("Unsatisfiable range")

    return (start, min(end, file_size - 1))


def list_available_videos() -> list[str]:
    video_dir = Path("videos")
    if not video_dir.exists():
        return []
    return sorted(
        file.name
        for file in video_dir.glob("*")
        if file.suffix.lower() in [".mp4", ".mov", ".mkv", ".hevc"]
    )


def list_available_schedules() -> list[str]:
    # Check current directory for JSON schedules
    return sorted(
        file.name
        for file in Path(".").glob("*.json")
        if file.name != "package.json" and file.name != "package-lock.json"
    )


def update_runtime_from_config() -> None:
    enable_system_logging(config.enable_system_logging or config.debug_mode)
    
    available = list_available_videos()
    configured_basename = os.path.basename(config.video_file) if config.video_file else ""
    
    # Priority 1: Configured file
    if configured_basename in available:
        cluster_state.current_video = configured_basename
    # Priority 2: sync_test.mp4
    elif "sync_test.mp4" in available:
        cluster_state.current_video = "sync_test.mp4"
    # Priority 3: First available
    elif available:
        cluster_state.current_video = available[0]
        log_info(f"Configured video '{configured_basename}' not found. Falling back to '{available[0]}'", component="remote")
    else:
        log_warning("No videos found in 'videos/' directory.", component="remote")


def build_config_snapshot(device_id: str, role: str, manager: ConfigManager) -> Dict[str, Any]:
    # We use a hash or just the values to detect real changes if we want to be fancy,
    # but for now, we just ensure we don't clobber 'updated_at' on every poll.
    return {
        "device_id": device_id,
        "role": role,
        "config_path": manager.get_config_path() or f"{role}_config.ini",
        "fields": manager.get_editable_fields(role),
        "values": manager.get_editable_values(role),
        "updated_at": time.time(),
    }


def refresh_local_snapshot() -> Dict[str, Any]:
    # Only rebuild if not exists or explicitly needed
    if LOCAL_LEADER_ID not in config_snapshots:
        config_snapshots[LOCAL_LEADER_ID] = build_config_snapshot(LOCAL_LEADER_ID, "leader", config)
    return config_snapshots[LOCAL_LEADER_ID]


def store_config_message(payload: Dict[str, Any]) -> None:
    device_id = payload.get("device_id")
    if not device_id:
        return

    # Update snapshot values but keep track of when they actually arrived
    existing_snapshot = config_snapshots.get(device_id, {})
    config_snapshots[device_id] = {**existing_snapshot, **payload, "updated_at": time.time()}
    config_messages[device_id] = {
        "status": payload.get("status", "ok"),
        "error": payload.get("error"),
        "requires_restart": payload.get("requires_restart", False),
        "updated_at": time.time(),
    }


def build_ui_state() -> Dict[str, Any]:
    refresh_local_snapshot()
    collaborators = command_manager.get_collaborators()
    avg_rtt = command_manager.get_average_rtt()

    if not cluster_state.is_playing:
        current_status = "Stopped"
    elif not cluster_state.is_master:
        current_status = "Syncing"
    else:
        current_status = "Leading"

    devices = [
        {
            "device_id": LOCAL_LEADER_ID,
            "label": "Simulated leader",
            "role": "leader",
            "ip": "localhost",
            "status": "leading" if cluster_state.is_master else "ready",
            "online": True,
            "latency_ms": round(avg_rtt * 1000, 1) if avg_rtt > 0 else None,
            "config": config_snapshots.get(LOCAL_LEADER_ID),
            "message": config_messages.get(LOCAL_LEADER_ID),
            "media": media_snapshots.get(LOCAL_LEADER_ID, []),
        }
    ]

    known_collaborator_ids = set(collaborators)
    known_collaborator_ids.update(
        device_id
        for device_id, snapshot in config_snapshots.items()
        if device_id != LOCAL_LEADER_ID and snapshot.get("role") == "collaborator"
    )
    known_collaborator_ids.update(
        device_id for device_id in config_messages if device_id != LOCAL_LEADER_ID
    )

    for device_id in sorted(known_collaborator_ids):
        info = collaborators.get(device_id, {})
        devices.append(
            {
                "device_id": device_id,
                "label": device_id,
                "role": "collaborator",
                "ip": info.get("ip", "unknown"),
                "status": info.get("status", "unknown"),
                "online": info.get("online", False),
                "video_file": info.get("video_file", ""),
                "latency_ms": round(command_manager.get_device_average_rtt(device_id) * 1000, 1)
                if command_manager.get_device_average_rtt(device_id) > 0
                else None,
                "config": config_snapshots.get(device_id),
                "message": config_messages.get(device_id),
                "media": media_snapshots.get(device_id, []),
            }
        )

    return {
        "video_pos": cluster_state.video_pos,
        "duration": cluster_state.duration,
        "status": current_status,
        "is_playing": cluster_state.is_playing,
        "is_master": cluster_state.is_master,
        "current_video": cluster_state.current_video,
        "available_videos": list_available_videos(),
        "available_schedules": list_available_schedules(),
        "devices": devices,
        "leader_media": video_manager.list_videos(),
    }


class RemoteHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args) -> None:
        if config.debug_mode or config.enable_system_logging:
            super().log_message(format, *args)

    def _send_json(self, payload: Dict[str, Any], status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode())

    def _send_file_range(self, file_path: Path) -> None:
        file_size = file_path.stat().st_size
        range_header = self.headers.get("Range")

        try:
            byte_range = resolve_byte_range(range_header, file_size)
        except ValueError:
            self.send_response(416)
            self.send_header("Content-Range", f"bytes */{file_size}")
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()
            return

        start = 0
        end = file_size - 1
        status = 200
        if byte_range is not None:
            start, end = byte_range
            status = 206

        # Dynamic MIME type
        mime_type = "video/mp4"
        ext = file_path.suffix.lower()
        if ext == ".mov":
            mime_type = "video/quicktime"
        elif ext == ".mkv":
            mime_type = "video/x-matroska"
        elif ext == ".webm":
            mime_type = "video/webm"

        self.send_response(status)
        self.send_header("Content-type", mime_type)
        self.send_header("Content-Length", str(end - start + 1))
        self.send_header("Accept-Ranges", "bytes")
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
        self.end_headers()

        with open(file_path, "rb") as file_handle:
            file_handle.seek(start)
            remaining = end - start + 1
            while remaining > 0:
                chunk = file_handle.read(min(64 * 1024, remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)

    def _read_json_body(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode())
        except json.JSONDecodeError:
            return {}

    def _handle_upload(self):
        """Handle multipart/form-data upload"""
        content_type = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in content_type:
            self._send_json({"status": "error", "message": "Expected multipart/form-data"}, status=400)
            return

        boundary = content_type.split("boundary=")[1].encode()
        length = int(self.headers.get("Content-Length"))
        
        input_data = self.rfile.read(length)
        parts = input_data.split(b"--" + boundary)
        
        file_data = None
        filename = None
        
        for part in parts:
            if b"Content-Disposition" in part and b"filename=" in part:
                headers, body = part.split(b"\r\n\r\n", 1)
                if body.endswith(b"\r\n"):
                    body = body[:-2]
                
                file_data = body
                
                for line in headers.decode().split("\r\n"):
                    if "Content-Disposition" in line and "filename=" in line:
                        filename = line.split("filename=")[1].strip('"')
                        break
        
        if filename and file_data:
            target_dir = video_manager.get_primary_video_dir()
            target_path = os.path.join(target_dir, filename)
            
            with open(target_path, "wb") as f:
                f.write(file_data)
            
            log_info(f"Uploaded file saved to: {target_path}", "remote")
            
            # If a target device was specified, trigger a sync/download to that device
            parsed_path = urlparse(self.path)
            query = parse_qs(parsed_path.query)
            target_device_id = query.get("target_device_id", [None])[0]
            
            if target_device_id and target_device_id != LOCAL_LEADER_ID:
                log_info(f"Triggering automatic sync for {filename} to {target_device_id}", "remote")
                
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                try:
                    s.connect(("8.8.8.8", 80))
                    leader_ip = s.getsockname()[0]
                finally:
                    s.close()
                    
                command_manager.send_command(
                    {
                        "type": "file_upload_notify",
                        "filename": filename,
                        "source_url": f"http://{leader_ip}:8080/api/media/download?filename={filename}",
                        "target_device_id": target_device_id
                    },
                    target_pi=target_device_id
                )

            self._send_json({"status": "ok", "filename": filename})
        else:
            self._send_json({"status": "error", "message": "No file found in request"}, status=400)

    def do_GET(self):
        parsed_path = urlparse(self.path)
        path = parsed_path.path

        if path == "/":
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            with open(TEMPLATE_DIR / "index.html", "rb") as f:
                self.wfile.write(f.read())
            return

        if path.startswith("/static/"):
            file_path = TEMPLATE_DIR / path.lstrip("/")
            # Check templates/static (new) and templates/templates/static (possible mistake)
            # Actually, the templates are in src/remote/templates/
            # Static is in src/remote/templates/static/
            if file_path.exists() and file_path.is_file():
                self.send_response(200)
                if file_path.suffix == ".css":
                    self.send_header("Content-type", "text/css")
                elif file_path.suffix == ".js":
                    self.send_header("Content-type", "application/javascript")
                self.end_headers()
                with open(file_path, "rb") as f:
                    self.wfile.write(f.read())
                return
            self.send_error(404)
            return

        if path in ["/state", "/json", "/api/state"]:
            self._send_json(build_ui_state())
            return

        if path == "/api/media/download":
            query = parse_qs(parsed_path.query)
            filename = query.get("filename", [None])[0]
            if not filename:
                self.send_error(400, "filename required")
                return
            
            all_videos = video_manager.list_videos()
            file_path = None
            for v in all_videos:
                if v["name"] == filename:
                    file_path = Path(v["path"])
                    break
            
            if not file_path or not file_path.exists():
                self.send_error(404, "File not found")
                return
                
            try:
                self._send_file_range(file_path)
            except Exception as exc:
                log_info(f"Download error: {exc}", component="remote")
            return

        if path.startswith("/video_file"):
            if not cluster_state.current_video:
                self.send_error(404, "No video selected")
                return
                
            video_path = Path("videos") / cluster_state.current_video
            if not video_path.exists():
                self.send_error(404, "Video file not found")
                return
            try:
                self._send_file_range(video_path)
            except (ConnectionResetError, BrokenPipeError):
                pass
            except Exception as exc:
                log_info(f"Stream error: {exc}", component="remote")
            return

        self.send_error(404)

    def do_DELETE(self):
        parsed_path = urlparse(self.path)
        action = parsed_path.path.strip("/")
        
        if action == "api/media":
            query = parse_qs(parsed_path.query)
            device_id = query.get("device_id", [None])[0]
            filename = query.get("filename", [None])[0]
            
            if not device_id or not filename:
                self._send_json({"status": "error", "message": "device_id and filename required"}, status=400)
                return
                
            if device_id == LOCAL_LEADER_ID:
                if video_manager.delete_video(filename):
                    self._send_json({"status": "ok"})
                else:
                    self._send_json({"status": "error", "message": "File not found"}, status=404)
                return
            
            command_manager.send_command(
                {"type": "file_delete_request", "filename": filename, "target_device_id": device_id},
                target_pi=device_id
            )
            self._send_json({"status": "requested"}, status=202)
            return

        self.send_error(404)

    def do_POST(self):
        parsed_path = urlparse(self.path)
        action = parsed_path.path.strip("/")
        query = parse_qs(parsed_path.query)
        
        if action == "api/media/upload":
            self._handle_upload()
            return

        payload = self._read_json_body()

        if action == "api/media/sync":
            device_id = payload.get("device_id")
            filename = payload.get("filename")
            if not device_id or not filename:
                self._send_json({"status": "error", "message": "device_id and filename required"}, status=400)
                return
            
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                s.connect(("8.8.8.8", 80))
                leader_ip = s.getsockname()[0]
            finally:
                s.close()
                
            command_manager.send_command(
                {
                    "type": "file_upload_notify",
                    "filename": filename,
                    "source_url": f"http://{leader_ip}:8080/api/media/download?filename={filename}",
                    "target_device_id": device_id
                },
                target_pi=device_id
            )
            self._send_json({"status": "requested"}, status=202)
            return

        if action == "api/media/request":
            device_id = payload.get("device_id")
            if not device_id:
                self._send_json({"status": "error", "message": "device_id required"}, status=400)
                return
            
            if device_id == LOCAL_LEADER_ID:
                media_snapshots[LOCAL_LEADER_ID] = video_manager.list_videos()
                self._send_json({"status": "ok", "media": media_snapshots[LOCAL_LEADER_ID]})
                return
                
            command_manager.send_command(
                {"type": "file_list_request", "target_device_id": device_id},
                target_pi=device_id
            )
            self._send_json({"status": "requested"}, status=202)
            return

        if action in {"play", "api/play"}:
            if leader_instance:
                leader_instance.start_system()
                self.send_response(204)
                self.end_headers()
                return

            cluster_state.is_playing = True
            cluster_state.is_master = True
            cluster_state.master_start_time = time.time()

            start_cmd = {
                "type": "start",
                "video_file": cluster_state.current_video,
                "start_time": cluster_state.master_start_time,
                "schedule": [],
                "debug_mode": config.debug_mode,
                "sync_params": {
                    "max_drift": config.max_drift,
                    "min_drift": config.min_drift,
                    "kp": config.kp,
                    "min_rate": config.min_rate,
                    "max_rate": config.max_rate,
                    "max_samples": config.max_samples,
                },
            }
            command_manager.send_command(start_cmd)
            log_info(f"Cluster PLAY: {cluster_state.current_video}", component="remote")
            self.send_response(204)
            self.end_headers()
            return

        if action in {"stop", "api/stop"}:
            if leader_instance:
                leader_instance.stop_system()
                self.send_response(204)
                self.end_headers()
                return

            cluster_state.is_playing = False
            cluster_state.is_master = False
            command_manager.send_command({"type": "stop"})
            log_info("Cluster STOP", component="remote")
            self.send_response(204)
            self.end_headers()
            return

        if action == "api/seek":
            new_pos = payload.get("value", 0)
            if leader_instance:
                leader_instance.seek_video(str(new_pos))
                self.send_response(204)
                self.end_headers()
                return

            cluster_state.video_pos = float(new_pos)
            cluster_state.master_start_time = time.time() - cluster_state.video_pos
            
            command_manager.send_command({"type": "remote_seek", "value": cluster_state.video_pos})
            log_info(f"Cluster SEEK: {cluster_state.video_pos:.2f}s", component="remote")
            self.send_response(204)
            self.end_headers()
            return

        if action == "api/set":
            param = payload.get("param")
            value = payload.get("value")
            
            if leader_instance:
                leader_instance.set_sync_param(param, value)
                self.send_response(204)
                self.end_headers()
                return

            command_manager.send_command({"type": "set", "param": param, "value": value})
            self.send_response(204)
            self.end_headers()
            return

        if action in {"set_video", "api/video"}:
            new_file = query.get("file", [None])[0]
            if new_file:
                cluster_state.current_video = new_file
                log_info(f"Video changed to: {new_file}", component="remote")
                if cluster_state.is_playing:
                    command_manager.send_command({"type": "stop"})
                    cluster_state.is_playing = False
            self.send_response(204)
            self.end_headers()
            return

        if action == "api/config/request":
            device_id = payload.get("device_id")
            if not device_id:
                self._send_json({"status": "error", "error": "device_id is required"}, status=400)
                return

            if device_id == LOCAL_LEADER_ID:
                self._send_json({"status": "ok", "config": refresh_local_snapshot()})
                return

            command_manager.send_command(
                {"type": "config_request", "target_device_id": device_id},
                target_pi=device_id,
            )
            self._send_json({"status": "requested"}, status=202)
            return

        if action == "api/config/save":
            device_id = payload.get("device_id")
            updates = payload.get("updates", {})
            if not device_id:
                self._send_json({"status": "error", "error": "device_id is required"}, status=400)
                return

            if device_id == LOCAL_LEADER_ID:
                editable_keys = {
                    field["key"] for field in config.get_editable_fields("leader")
                }
                filtered_updates = {
                    key: value for key, value in updates.items() if key in editable_keys
                }
                config.clean_and_save_config("leader_config.ini", filtered_updates, role="leader")
                update_runtime_from_config()
                
                config_snapshots[LOCAL_LEADER_ID] = build_config_snapshot(LOCAL_LEADER_ID, "leader", config)
                
                config_messages[LOCAL_LEADER_ID] = {
                    "status": "ok",
                    "requires_restart": False,
                    "updated_at": time.time(),
                }
                self._send_json({"status": "ok"})
                return

            command_manager.send_command(
                {
                    "type": "config_update",
                    "target_device_id": device_id,
                    "updates": updates,
                },
                target_pi=device_id,
            )
            self._send_json({"status": "requested"}, status=202)
            return

        if action == "api/config/reset":
            device_id = payload.get("device_id")
            if not device_id:
                self._send_json({"status": "error", "error": "device_id is required"}, status=400)
                return

            if device_id == LOCAL_LEADER_ID:
                defaults = config.get_default_values("leader")
                config.clean_and_save_config("leader_config.ini", defaults, role="leader")
                update_runtime_from_config()
                refresh_local_snapshot()
                config_messages[LOCAL_LEADER_ID] = {
                    "status": "ok",
                    "requires_restart": True,
                    "updated_at": time.time(),
                }
                self._send_json({"status": "ok"})
                return

            command_manager.send_command(
                {"type": "config_reset", "target_device_id": device_id},
                target_pi=device_id,
            )
            self._send_json({"status": "requested"}, status=202)
            return

        self.send_error(404)


class RobustRemoteServer(ThreadingHTTPServer):
    def handle_error(self, request, client_address):
        exctype, _value = sys.exc_info()[:2]
        if exctype in (ConnectionResetError, BrokenPipeError):
            return
        super().handle_error(request, client_address)


# Leader instance for integrated mode
leader_instance = None


def update_cluster_state(is_playing: bool, video_pos: float, duration: float, master_start_time: float, is_master: bool, current_video: str):
    global cluster_state
    cluster_state.is_playing = is_playing
    cluster_state.video_pos = video_pos
    cluster_state.duration = duration
    cluster_state.master_start_time = master_start_time
    cluster_state.is_master = is_master
    cluster_state.current_video = current_video


def set_shared_resources(shared_config, shared_command_manager, shared_sync_broadcaster, shared_leader=None):
    global config, command_manager, sync_broadcaster, video_manager, LOCAL_LEADER_ID, leader_instance
    config = shared_config
    command_manager = shared_command_manager
    sync_broadcaster = shared_sync_broadcaster
    leader_instance = shared_leader
    LOCAL_LEADER_ID = config.device_id
    video_manager = VideoFileManager(config.video_file, config.usb_mount_point)


def start_remote(integrated=False):
    """Start the remote controller services."""
    if not integrated:
        update_runtime_from_config()
        command_manager.start_listening()
        command_manager.start_latency_probing()
        sync_broadcaster.setup_socket()

    command_manager.register_handler("config_state", lambda msg, addr: store_config_message(msg))
    command_manager.register_handler(
        "config_update_result", lambda msg, addr: store_config_message(msg)
    )
    
    def store_media_message(payload):
        device_id = payload.get("device_id")
        if device_id:
            media_snapshots[device_id] = payload.get("media", [])
            
    command_manager.register_handler("file_list_response", lambda msg, addr: store_media_message(msg))

    def auto_discover(device_id, ip):
        log_info(f"Auto-discovered new device: {device_id} at {ip}. Requesting state...", component="remote")
        command_manager.send_command({"type": "file_list_request"}, target_pi=device_id)
        command_manager.send_command({"type": "config_request"}, target_pi=device_id)
        
    command_manager.on_device_discovered = auto_discover

    def master_clock():
        last_broadcast = 0.0
        while True:
            # When integrated with leader.py, cluster_state should be updated by leader.py
            # or we should just let leader.py handle its own broadcasting if it's the master.
            # However, for now, if integrated, we can just skip this loop if leader.py handles it.
            if integrated:
                # The standalone master_clock loop in leader.py or collaborator.py will handle this.
                # Actually, the remote controller has its OWN master_clock loop that 
                # handles the 'virtual' leader if it's acting as the leader itself.
                # If integrated with leader.py, leader.py is the leader.
                return 

            if cluster_state.is_master and cluster_state.is_playing:
                cluster_state.video_pos = time.time() - cluster_state.master_start_time

                if time.time() - last_broadcast > 2.0:
                    start_cmd = {
                        "type": "start",
                        "video_file": cluster_state.current_video,
                        "start_time": cluster_state.master_start_time,
                        "schedule": [],
                        "debug_mode": config.debug_mode,
                        "sync_params": {
                            "max_drift": config.max_drift,
                            "min_drift": config.min_drift,
                            "kp": config.kp,
                            "min_rate": config.min_rate,
                            "max_rate": config.max_rate,
                            "max_samples": config.max_samples,
                        },
                    }
                    command_manager.send_command(start_cmd)
                    last_broadcast = time.time()

                sync_packet = json.dumps(
                    {
                        "type": "sync",
                        "time": cluster_state.video_pos,
                        "leader_id": sync_broadcaster.leader_id,
                        "source": "wall",
                        "sent_at": time.time(),
                    }
                )
                sync_broadcaster.sync_sock.sendto(
                    sync_packet.encode(),
                    (sync_broadcaster.broadcast_ip, sync_broadcaster.sync_port),
                )

            time.sleep(config.tick_interval)

    threading.Thread(target=master_clock, daemon=True).start()

    web_thread = threading.Thread(
        target=lambda: RobustRemoteServer(("0.0.0.0", 8080), RemoteHandler).serve_forever(),
        daemon=True,
    )
    web_thread.start()

    log_info("Remote Controller Web UI available at http://localhost:8080", component="remote")
    if not integrated:
        log_info(f"Default video from config: {cluster_state.current_video}", component="remote")


if __name__ == "__main__":
    try:
        start_remote()
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        log_info("Shutting down remote controller...")
