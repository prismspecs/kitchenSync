#!/usr/bin/env python3
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse, quote
import socket

# Add parent directory to path to allow importing from src
sys.path.append(str(Path(__file__).resolve().parent.parent))

from config.manager import ConfigManager
from core.logger import enable_system_logging, log_info, log_warning, log_file_paths
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
config = ConfigManager("ksync_webui.ini")
video_manager = VideoFileManager(config.video_file, config.usb_mount_point)
command_manager = CommandManager()
sync_broadcaster = SyncBroadcaster()
sync_broadcaster.leader_id = LOCAL_LEADER_ID

config_snapshots: Dict[str, Dict[str, Any]] = {}
config_messages: Dict[str, Dict[str, Any]] = {}

# Log state caches
log_snapshots: Dict[str, str] = {}
log_events: Dict[str, threading.Event] = {}

# Media state cache
media_snapshots: Dict[str, List[Dict[str, Any]]] = {}

# Conversion job tracking
@dataclass
class ConversionJob:
    device_id: str
    status: str = "queued"  # queued, converting, uploading, complete, error
    convert_progress: float = 0.0  # 0–100
    upload_progress: float = 0.0   # 0–100
    output_filename: str = ""
    error: str = ""
    source_filename: str = ""
    target_codec: str = ""

_conversion_jobs: Dict[str, ConversionJob] = {}
_conversion_jobs_lock = threading.Lock()
CONVERT_TMP = Path("media/.convert_tmp")


def _find_real_leader() -> Optional[str]:
    """Return device_id of a Pi leader, or None if the web UI is the leader."""
    for device_id, snapshot in config_snapshots.items():
        if device_id == LOCAL_LEADER_ID:
            continue
        if snapshot.get("role") == "leader":
            return device_id
    return None


def _update_device(device_id: str) -> None:
    """Send a device_update command over UDP — the Pi handles git pull && reboot locally."""
    if device_id == LOCAL_LEADER_ID:
        log_info("Device update requested for leader — running locally", component="remote")

        def _do_update():
            repo = Path(__file__).resolve().parent.parent.parent
            try:
                subprocess.run(
                    ["git", "pull"],
                    cwd=str(repo), capture_output=True, text=True, timeout=30,
                )
            except Exception as e:
                log_warning(f"Leader update git pull failed: {e}", component="remote")
            subprocess.run(["sudo", "reboot"], capture_output=True)

        threading.Thread(target=_do_update, daemon=True).start()
    else:
        command_manager.send_command(
            {"type": "device_update", "target_device_id": device_id},
            target_pi=device_id,
        )
        log_info(f"Device update sent to {device_id}", component="remote")


def compute_latency_compensation(avg_rtt: float, enabled: bool, latency_factor: float) -> float:
    """Return the leader sync pre-advance in seconds."""
    if not enabled or avg_rtt <= 0:
        return 0.0
    return avg_rtt * latency_factor

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
    video_dir = Path("media")
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


def _get_target_codec(pi_model: str) -> str:
    if "Raspberry Pi 4" in pi_model:
        return "h264"
    return "hevc"


def _get_conversion_job(device_id: str) -> Optional[ConversionJob]:
    with _conversion_jobs_lock:
        return _conversion_jobs.get(device_id)


def _set_conversion_job(job: ConversionJob) -> None:
    with _conversion_jobs_lock:
        _conversion_jobs[job.device_id] = job


def _run_conversion(source_path: Path, output_path: Path, target_codec: str, device_id: str) -> bool:
    """Run ffmpeg conversion with progress tracking. Returns True on success."""
    job = _get_conversion_job(device_id)
    if not job:
        return False

    fps = 30.0
    try:
        probe = subprocess.run(
            ["ffprobe", "-v", "0", "-of", "csv=p=0", "-select_streams", "v:0",
             "-show_entries", "stream=avg_frame_rate", str(source_path)],
            capture_output=True, text=True, timeout=10,
        )
        if probe.returncode == 0 and probe.stdout.strip():
            match = re.match(r"(\d+)/(\d+)", probe.stdout.strip())
            if match:
                fps = float(match.group(1)) / float(match.group(2))
    except Exception:
        pass

    keyint = max(int(round(fps)), 1)
    log_info(f"Convert: detected fps={fps:.2f}, keyint={keyint} for {device_id}", component="remote")

    if target_codec == "h264":
        cmd = [
            "ffmpeg", "-y",
            "-i", str(source_path),
            "-an",
            "-vf", f"fps={fps:.2f},format=yuv420p",
            "-c:v", "libx264",
            "-profile:v", "high",
            "-level", "4.2",
            "-preset", "slow",
            "-x264-params", f"keyint={keyint}:min-keyint={keyint}:scenecut=0",
            "-b:v", "10M", "-maxrate", "12M", "-bufsize", "20M",
            "-progress", "pipe:1",
            "-nostats",
            str(output_path),
        ]
    else:
        cmd = [
            "ffmpeg", "-y",
            "-i", str(source_path),
            "-an",
            "-vf", f"fps={fps:.2f},format=yuv420p",
            "-c:v", "libx265",
            "-preset", "medium",
            "-tag:v", "hvc1",
            "-x265-params", f"keyint={keyint}:min-keyint={keyint}:scenecut=0",
            "-b:v", "10M", "-maxrate", "12M", "-bufsize", "20M",
            "-progress", "pipe:1",
            "-nostats",
            str(output_path),
        ]

    # Get source duration for progress calculation
    duration = 0.0
    try:
        dur_probe = subprocess.run(
            ["ffprobe", "-v", "0", "-of", "csv=p=0", "-select_streams", "v:0",
             "-show_entries", "format=duration", str(source_path)],
            capture_output=True, text=True, timeout=10,
        )
        if dur_probe.returncode == 0 and dur_probe.stdout.strip():
            duration = float(dur_probe.stdout.strip())
    except Exception:
        pass

    if duration <= 0:
        duration = 30.0  # fallback

    log_info(f"Convert: starting ffmpeg for {device_id} ({target_codec}), duration={duration:.1f}s", component="remote")

    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )

        for line in proc.stdout:
            line = line.strip()
            if line.startswith("out_time_us=") or line.startswith("out_time_usec="):
                try:
                    usec = int(line.split("=")[1])
                    pct = min(usec / 1_000_000 / duration * 100, 99.9)
                    job.convert_progress = round(pct, 1)
                    _set_conversion_job(job)
                except (ValueError, ZeroDivisionError):
                    pass

        proc.wait(timeout=3600)

        if proc.returncode != 0:
            stderr = proc.stderr.read()[:500] if proc.stderr else ""
            job.status = "error"
            job.error = f"ffmpeg failed (code {proc.returncode}): {stderr}"
            _set_conversion_job(job)
            log_warning(f"Convert: ffmpeg error for {device_id}: {job.error}", component="remote")
            return False

        job.convert_progress = 100.0
        _set_conversion_job(job)
        log_info(f"Convert: completed for {device_id} -> {output_path.name}", component="remote")
        return True

    except subprocess.TimeoutExpired:
        job.status = "error"
        job.error = "ffmpeg timed out after 1 hour"
        _set_conversion_job(job)
        return False
    except FileNotFoundError:
        job.status = "error"
        job.error = "ffmpeg not found on this system"
        _set_conversion_job(job)
        return False
    except Exception as e:
        job.status = "error"
        job.error = f"Conversion failed: {e}"
        _set_conversion_job(job)
        return False


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
        log_warning("No media found in 'media/' directory.", component="remote")


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

    log_info(f"Config: received config_state from {device_id}", component="remote")

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
    compensation = compute_latency_compensation(
        avg_rtt,
        config.enable_latency_compensation,
        config.latency_factor,
    )

    if not cluster_state.is_playing:
        current_status = "Stopped"
    elif not cluster_state.is_master:
        current_status = "Syncing"
    else:
        current_status = "Leading"

    leader_video = cluster_state.current_video
    leader_optimized = False
    if leader_video:
        leader_video_path = video_manager.find_video_file(leader_video)
        if leader_video_path:
            meta = video_manager.get_metadata(leader_video_path)
            leader_optimized = meta.get("is_optimized", False)

    local_config = config_snapshots.get(LOCAL_LEADER_ID, {})
    devices = [
        {
            "device_id": LOCAL_LEADER_ID,
            "label": "This computer",
            "role": config.role_name(),
            "ip": "localhost",
            "status": "leading" if cluster_state.is_master else "ready",
            "online": True,
            "latency_ms": round(avg_rtt * 1000, 1) if avg_rtt > 0 else None,
            "config": local_config,
            "message": config_messages.get(LOCAL_LEADER_ID),
            "media": media_snapshots.get(LOCAL_LEADER_ID, []),
            "video_file": leader_video,
            "video_driver": local_config.get("video_driver", config.video_driver),
            "is_optimized": leader_optimized,
            "pi_model": "",
        }
    ]

    # Prune stale config snapshots/messages for device IDs no longer in the
    # live collaborators list (handles device renames gracefully).
    now = time.time()
    for device_id in list(config_snapshots.keys()):
        if device_id != LOCAL_LEADER_ID and device_id not in collaborators:
            if now - config_snapshots[device_id].get("updated_at", 0) > 300:
                del config_snapshots[device_id]
    for device_id in list(config_messages.keys()):
        if device_id != LOCAL_LEADER_ID and device_id not in collaborators:
            if now - config_messages[device_id].get("updated_at", 0) > 300:
                del config_messages[device_id]

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
        snapshot = config_snapshots.get(device_id, {})
        devices.append(
            {
                "device_id": device_id,
                "label": device_id,
                "role": snapshot.get("role", "collaborator"),
                "ip": info.get("ip", "unknown"),
                "status": info.get("status", "unknown"),
                "online": info.get("online", False),
                "video_file": info.get("video_file", ""),
                "video_driver": info.get("video_driver", snapshot.get("video_driver", "")),
                "is_optimized": info.get("is_optimized", False),
                "hard_seeks": info.get("hard_seeks", 0),
                "sync_deviation": info.get("sync_deviation", 0.0),
                "playback_rate": info.get("playback_rate", 1.0),
                "latency_ms": round(command_manager.get_device_average_rtt(device_id) * 1000, 1)
                if command_manager.get_device_average_rtt(device_id) > 0
                else None,
                "config": config_snapshots.get(device_id),
                "message": config_messages.get(device_id),
                "media": media_snapshots.get(device_id),
                "pi_model": info.get("pi_model", ""),
            }
        )

    return {
        "video_pos": max(0.0, cluster_state.video_pos - getattr(config, "emulated_render_lag", 0.05)),
        "duration": cluster_state.duration,
        "status": current_status,
        "is_playing": cluster_state.is_playing,
        "is_master": cluster_state.is_master,
        "current_video": cluster_state.current_video,
        "latency": {
            "enabled": config.enable_latency_compensation,
            "avg_rtt_ms": round(avg_rtt * 1000, 1) if avg_rtt > 0 else None,
            "compensation_ms": round(compensation * 1000, 1),
        },
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
            video_manager.trigger_background_scan(force=True)
            
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
                        "source_url": f"http://{leader_ip}:8080/api/media/download?filename={quote(filename)}",
                        "target_device_id": target_device_id
                    },
                    target_pi=target_device_id
                )

            self._send_json({"status": "ok", "filename": filename})
        else:
            self._send_json({"status": "error", "message": "No file found in request"}, status=400)

    def _handle_convert_and_upload(self):
        """Handle multipart upload with on-the-fly codec conversion for target device."""
        content_type = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in content_type:
            self._send_json({"status": "error", "message": "Expected multipart/form-data"}, status=400)
            return

        parsed_path = urlparse(self.path)
        query = parse_qs(parsed_path.query)
        target_device_id = query.get("target_device_id", [None])[0]
        if not target_device_id:
            self._send_json({"status": "error", "message": "target_device_id required"}, status=400)
            return

        # Check for existing job
        existing = _get_conversion_job(target_device_id)
        if existing and existing.status in ("queued", "converting", "uploading"):
            self._send_json({"status": "error", "message": "A conversion is already in progress for this device"}, status=409)
            return

        # Get device info and determine target codec
        collaborators = command_manager.get_collaborators()
        device_info = collaborators.get(target_device_id, {})
        pi_model = device_info.get("pi_model", "")
        target_codec = _get_target_codec(pi_model)
        log_info(f"Convert: target={target_device_id} pi_model='{pi_model}' codec={target_codec}", component="remote")

        # Parse the uploaded file
        boundary = content_type.split("boundary=")[1].encode()
        length = int(self.headers.get("Content-Length"))
        input_data = self.rfile.read(length)
        parts = input_data.split(b"--" + boundary)

        file_data = None
        source_filename = None
        for part in parts:
            if b"Content-Disposition" in part and b"filename=" in part:
                headers, body = part.split(b"\r\n\r\n", 1)
                if body.endswith(b"\r\n"):
                    body = body[:-2]
                file_data = body
                for line in headers.decode().split("\r\n"):
                    if "Content-Disposition" in line and "filename=" in line:
                        source_filename = line.split("filename=")[1].strip('"')
                        break

        if not source_filename or not file_data:
            self._send_json({"status": "error", "message": "No file found in request"}, status=400)
            return

        # Save source file temporarily
        CONVERT_TMP.mkdir(parents=True, exist_ok=True)
        source_stem = Path(source_filename).stem
        safe_stem = re.sub(r'[^a-zA-Z0-9_-]', '_', source_stem)
        source_path = CONVERT_TMP / f"{uuid.uuid4().hex}_{safe_stem}{Path(source_filename).suffix}"
        with open(source_path, "wb") as f:
            f.write(file_data)

        # Determine output filename
        codec_tag = f"pi5_hevc" if target_codec == "hevc" else "pi4_h264"
        output_filename = f"{safe_stem}_{codec_tag}.mp4"
        output_path = Path("media") / output_filename

        # Create job record
        job = ConversionJob(
            device_id=target_device_id,
            status="converting",
            source_filename=source_filename,
            output_filename=output_filename,
            target_codec=target_codec,
        )
        _set_conversion_job(job)

        # Run conversion in background
        def _do_conversion():
            job = _get_conversion_job(target_device_id)
            if not job:
                return

            try:
                success = _run_conversion(source_path, output_path, target_codec, target_device_id)
                if not success:
                    return

                # Conversion done, trigger upload to target device
                job.status = "uploading"
                _set_conversion_job(job)

                # Trigger file sync to the target device
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                try:
                    s.connect(("8.8.8.8", 80))
                    leader_ip = s.getsockname()[0]
                finally:
                    s.close()

                command_manager.send_command(
                    {
                        "type": "file_upload_notify",
                        "filename": output_filename,
                        "source_url": f"http://{leader_ip}:8080/api/media/download?filename={quote(output_filename)}",
                        "target_device_id": target_device_id,
                    },
                    target_pi=target_device_id,
                )

                # Trigger a media scan so the file appears locally
                video_manager.trigger_background_scan(force=True)

                job.status = "complete"
                job.upload_progress = 100.0
                _set_conversion_job(job)
                log_info(f"Convert+Upload: complete for {target_device_id} -> {output_filename}", component="remote")

            except Exception as e:
                job.status = "error"
                job.error = str(e)
                _set_conversion_job(job)
                log_warning(f"Convert+Upload: failed for {target_device_id}: {e}", component="remote")
            finally:
                # Clean up source temp file
                try:
                    if source_path.exists():
                        source_path.unlink()
                except Exception:
                    pass

        threading.Thread(target=_do_conversion, daemon=True).start()

        self._send_json({
            "status": "started",
            "job": {
                "device_id": target_device_id,
                "output_filename": output_filename,
                "target_codec": target_codec,
            },
        })

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
                
            video_path = Path("media") / cluster_state.current_video
            if not video_path.exists():
                self.send_error(404, "Media file not found")
                return
            try:
                self._send_file_range(video_path)
            except (ConnectionResetError, BrokenPipeError):
                pass
            except Exception as exc:
                log_info(f"Stream error: {exc}", component="remote")
            return

        if path == "/api/media/convert-status":
            query = parse_qs(parsed_path.query)
            device_id = query.get("device_id", [None])[0]
            if not device_id:
                self._send_json({"status": "error", "message": "device_id required"}, status=400)
                return
            job = _get_conversion_job(device_id)
            if not job:
                self._send_json({"status": "not_found"})
                return
            self._send_json({
                "status": job.status,
                "convert_progress": job.convert_progress,
                "upload_progress": job.upload_progress,
                "output_filename": job.output_filename,
                "source_filename": job.source_filename,
                "target_codec": job.target_codec,
                "error": job.error,
            })
            return

        if path == "/api/logs":
            query = parse_qs(parsed_path.query)
            device_id = query.get("device_id", [None])[0]
            if not device_id:
                self._send_json({"status": "error", "message": "device_id required"}, status=400)
                return

            if device_id == LOCAL_LEADER_ID:
                try:
                    log_paths = log_file_paths()
                    sys_log_path = log_paths.get("system", "logs/kitchensync.log")
                    if os.path.exists(sys_log_path):
                        with open(sys_log_path, "r", errors="replace") as f:
                            lines = f.readlines()
                            log_content = "".join(lines[-100:])
                            if len(log_content) > 30000:
                                log_content = "... [TRUNCATED] ...\n" + log_content[-30000:]
                    else:
                        log_content = "No log file found on leader."
                    self._send_json({"status": "ok", "logs": log_content})
                except Exception as exc:
                    self._send_json({"status": "error", "message": f"Failed to read leader logs: {exc}"}, status=500)
                return
            else:
                event = threading.Event()
                log_events[device_id] = event
                
                if device_id in log_snapshots:
                    del log_snapshots[device_id]
                
                command_manager.send_command(
                    {"type": "log_request", "target_device_id": device_id},
                    target_pi=device_id
                )
                
                event_set = event.wait(1.5)
                if event_set and device_id in log_snapshots:
                    self._send_json({"status": "ok", "logs": log_snapshots[device_id]})
                else:
                    cached_log = log_snapshots.get(device_id, "Timeout: No response from collaborator.")
                    self._send_json({"status": "ok", "logs": cached_log})
                
                if device_id in log_events:
                    del log_events[device_id]
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

        if action == "api/media/convert-and-upload":
            self._handle_convert_and_upload()
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
                    "source_url": f"http://{leader_ip}:8080/api/media/download?filename={quote(filename)}",
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
            # If there's a real Pi leader, delegate to it instead of broadcasting.
            real_leader = _find_real_leader()
            if real_leader:
                command_manager.send_command(
                    {"type": "remote_start"},
                    target_pi=real_leader,
                )
                log_info(f"Delegated play to leader {real_leader}", component="remote")
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
            real_leader = _find_real_leader()
            if real_leader:
                command_manager.send_command(
                    {"type": "remote_stop"},
                    target_pi=real_leader,
                )
                log_info(f"Delegated stop to leader {real_leader}", component="remote")
            else:
                command_manager.send_command({"type": "stop"})
            cluster_state.is_playing = False
            cluster_state.is_master = False
            log_info("Cluster STOP", component="remote")
            self.send_response(204)
            self.end_headers()
            return

        if action == "api/seeks/reset":
            for device_id, info in command_manager.collaborators.items():
                info["hard_seeks"] = 0
            command_manager.send_command({"type": "reset_seeks"})
            log_info("Cluster: Reset seeks command sent to all collaborators", component="remote")
            self.send_response(204)
            self.end_headers()
            return

        if action == "api/seek":
            new_pos = payload.get("value", 0)
            cluster_state.video_pos = float(new_pos)
            cluster_state.master_start_time = time.time() - cluster_state.video_pos
            
            command_manager.send_command({"type": "remote_seek", "value": cluster_state.video_pos})
            log_info(f"Cluster SEEK: {cluster_state.video_pos:.2f}s", component="remote")
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
                config.clean_and_save_config("ksync_webui.ini", filtered_updates, role="leader")
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
                config.clean_and_save_config("ksync_webui.ini", defaults, role="leader")
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

        if action == "api/media/load":
            device_id = payload.get("device_id")
            filename = payload.get("filename")
            if not device_id or not filename:
                self._send_json({"status": "error", "message": "device_id and filename required"}, status=400)
                return

            if device_id == LOCAL_LEADER_ID:
                cluster_state.current_video = filename
                log_info(f"Video changed to: {filename}", component="remote")
                if cluster_state.is_playing:
                    command_manager.send_command({"type": "stop"})
                    cluster_state.is_playing = False
                self._send_json({"status": "ok"})
                return

            # Persist as the device's configured video_file; the device saves
            # and restarts itself (leader restarts on video change, collaborator
            # restarts on any config update), then playback resumes with the
            # new file via the normal start-command flow.
            log_info(f"Load video '{filename}' on {device_id}", component="remote")
            command_manager.send_command(
                {
                    "type": "config_update",
                    "target_device_id": device_id,
                    "updates": {"video_file": filename},
                },
                target_pi=device_id,
            )
            self._send_json({"status": "requested"}, status=202)
            return

        if action == "api/device/update":
            device_id = payload.get("device_id")
            if not device_id:
                self._send_json({"status": "error", "message": "device_id required"}, status=400)
                return
            threading.Thread(target=_update_device, args=(device_id,), daemon=True).start()
            self._send_json({"status": "started", "message": "Update initiated"})
            return

        self.send_error(404)


class RobustRemoteServer(ThreadingHTTPServer):
    def handle_error(self, request, client_address):
        exctype, _value = sys.exc_info()[:2]
        if exctype in (ConnectionResetError, BrokenPipeError):
            return
        super().handle_error(request, client_address)


def _handle_leader_announce(msg: Dict[str, Any], addr: tuple) -> None:
    device_id = msg.get("device_id")
    if not device_id:
        return
    log_info(f"Discover: leader_announce from {device_id} at {addr[0]}", component="remote")
    command_manager.collaborators[device_id] = {
        "ip": addr[0],
        "last_seen": time.time(),
        "status": msg.get("status", "leader"),
        "video_file": msg.get("video_file", ""),
        "video_driver": msg.get("video_driver", ""),
        "is_optimized": msg.get("is_optimized", False),
        "hard_seeks": 0,
        "pi_model": msg.get("pi_model", ""),
    }


def start_remote():
    """Start the remote controller services."""
    update_runtime_from_config()

    command_manager.register_handler("leader_announce", lambda msg, addr: _handle_leader_announce(msg, addr))
    command_manager.register_handler("config_state", lambda msg, addr: store_config_message(msg))
    command_manager.register_handler(
        "config_update_result", lambda msg, addr: store_config_message(msg)
    )
    
    def store_media_message(payload):
        device_id = payload.get("device_id")
        if device_id:
            media_snapshots[device_id] = payload.get("media", [])
            
    command_manager.register_handler("file_list_response", lambda msg, addr: store_media_message(msg))

    def store_log_message(payload):
        device_id = payload.get("device_id")
        if device_id:
            log_snapshots[device_id] = payload.get("logs", "")
            if device_id in log_events:
                log_events[device_id].set()

    command_manager.register_handler("log_response", lambda msg, addr: store_log_message(msg))

    sync_broadcaster.setup_socket()

    def master_clock():
        last_broadcast = 0.0
        last_send_error_at = 0.0
        while True:
            if cluster_state.is_master and cluster_state.is_playing:
                cluster_state.video_pos = time.time() - cluster_state.master_start_time
                compensation = 0.0

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
                        "time": cluster_state.video_pos + compensation,
                        "leader_id": sync_broadcaster.leader_id,
                        "source": "wall",
                        "sent_at": time.time(),
                    }
                )
                try:
                    sync_broadcaster.sync_sock.sendto(
                        sync_packet.encode(),
                        (sync_broadcaster.broadcast_ip, sync_broadcaster.sync_port),
                    )
                except Exception as e:
                    if time.time() - last_send_error_at > 5.0:
                        log_warning(f"Remote: Failed to broadcast sync packet: {e}", component="remote")
                        last_send_error_at = time.time()

            time.sleep(config.tick_interval)

    threading.Thread(target=master_clock, daemon=True).start()

    command_manager.start_listening()
    command_manager.start_latency_probing()

    # Periodically broadcast discovery so leaders respond via unicast
    def _discover_loop():
        while True:
            log_info("Discover: broadcasting...", component="remote")
            command_manager.send_command({"type": "discover", "device_id": LOCAL_LEADER_ID})
            time.sleep(10)

    threading.Thread(target=_discover_loop, daemon=True).start()

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
