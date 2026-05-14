#!/usr/bin/env python3
import json
import os
import shutil
import sys
import threading
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict
from urllib.parse import parse_qs, urlparse

# Add parent directory to path to allow importing from src
sys.path.append(str(Path(__file__).resolve().parent.parent))

from config.manager import ConfigManager
from core.logger import enable_system_logging, log_info
from networking.communication import CommandManager, SyncBroadcaster


@dataclass
class ClusterState:
    is_playing: bool = False
    video_pos: float = 0.0
    duration: float = 0.0
    master_start_time: float = 0.0
    is_master: bool = False
    current_video: str = "test_video.mp4"


LOCAL_LEADER_ID = "remote-leader"

cluster_state = ClusterState()
config = ConfigManager("leader_config.ini")
command_manager = CommandManager()
sync_broadcaster = SyncBroadcaster()
sync_broadcaster.leader_id = LOCAL_LEADER_ID

config_snapshots: Dict[str, Dict[str, Any]] = {}
config_messages: Dict[str, Dict[str, Any]] = {}

TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"


def list_available_videos() -> list[str]:
    video_dir = Path("videos")
    if not video_dir.exists():
        return []
    return sorted(
        file.name
        for file in video_dir.glob("*")
        if file.suffix.lower() in [".mp4", ".mov", ".mkv", ".hevc"]
    )


def update_runtime_from_config() -> None:
    enable_system_logging(config.enable_system_logging or config.debug_mode)
    if config.video_file:
        cluster_state.current_video = os.path.basename(config.video_file)


def build_config_snapshot(device_id: str, role: str, manager: ConfigManager) -> Dict[str, Any]:
    return {
        "device_id": device_id,
        "role": role,
        "config_path": manager.get_config_path() or f"{role}_config.ini",
        "fields": manager.get_editable_fields(role),
        "values": manager.get_editable_values(role),
        "updated_at": time.time(),
    }


def refresh_local_snapshot() -> Dict[str, Any]:
    snapshot = build_config_snapshot(LOCAL_LEADER_ID, "leader", config)
    config_snapshots[LOCAL_LEADER_ID] = snapshot
    return snapshot


def store_config_message(payload: Dict[str, Any]) -> None:
    device_id = payload.get("device_id")
    if not device_id:
        return

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

    if not cluster_state.is_playing:
        current_status = "Stopped"
    elif not cluster_state.is_master:
        current_status = "Disconnected"
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
            "config": config_snapshots.get(LOCAL_LEADER_ID),
            "message": config_messages.get(LOCAL_LEADER_ID),
        }
    ]

    for device_id, info in collaborators.items():
        devices.append(
            {
                "device_id": device_id,
                "label": device_id,
                "role": "collaborator",
                "ip": info.get("ip", "unknown"),
                "status": info.get("status", "unknown"),
                "online": info.get("online", False),
                "video_file": info.get("video_file", ""),
                "config": config_snapshots.get(device_id),
                "message": config_messages.get(device_id),
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
        "devices": devices,
    }


class RemoteHandler(BaseHTTPRequestHandler):
    def _send_json(self, payload: Dict[str, Any], status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode())

    def _read_json_body(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode())
        except json.JSONDecodeError:
            return {}

    def do_GET(self):
        if self.path == "/":
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            with open(TEMPLATE_DIR / "index.html", "rb") as f:
                self.wfile.write(f.read())
            return

        if self.path.startswith("/static/"):
            file_path = TEMPLATE_DIR / self.path.lstrip("/")
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

        if self.path in ["/state", "/json", "/api/state"]:
            self._send_json(build_ui_state())
            return

        if self.path.startswith("/video_file"):
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
                with open(video_path, "rb") as file_handle:
                    shutil.copyfileobj(file_handle, self.wfile)
            except (ConnectionResetError, BrokenPipeError):
                pass
            except Exception as exc:
                log_info(f"Stream error: {exc}", component="remote")
            return

        self.send_error(404)

    def do_POST(self):
        parsed_path = urlparse(self.path)
        action = parsed_path.path.strip("/")
        query = parse_qs(parsed_path.query)
        payload = self._read_json_body()

        if action in {"play", "api/play"}:
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
            cluster_state.is_playing = False
            cluster_state.is_master = False
            command_manager.send_command({"type": "stop"})
            log_info("Cluster STOP", component="remote")
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
                refresh_local_snapshot()
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

        self.send_error(404)


class RobustRemoteServer(ThreadingHTTPServer):
    def handle_error(self, request, client_address):
        exctype, _value = sys.exc_info()[:2]
        if exctype in (ConnectionResetError, BrokenPipeError):
            return
        super().handle_error(request, client_address)


def start_remote():
    """Start the remote controller services."""
    update_runtime_from_config()

    command_manager.register_handler("config_state", lambda msg, addr: store_config_message(msg))
    command_manager.register_handler(
        "config_update_result", lambda msg, addr: store_config_message(msg)
    )

    sync_broadcaster.setup_socket()

    def master_clock():
        last_broadcast = 0.0
        while True:
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
                    }
                )
                sync_broadcaster.sync_sock.sendto(
                    sync_packet.encode(),
                    (sync_broadcaster.broadcast_ip, sync_broadcaster.sync_port),
                )

            time.sleep(config.tick_interval)

    threading.Thread(target=master_clock, daemon=True).start()

    command_manager.start_listening()

    web_thread = threading.Thread(
        target=lambda: RobustRemoteServer(("0.0.0.0", 8080), RemoteHandler).serve_forever(),
        daemon=True,
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
