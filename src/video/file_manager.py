#!/usr/bin/env python3
"""
Video File Discovery and Management for kSync
Handles finding and managing video files from various sources
"""

import glob
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Optional, List

from core.logger import log_info, log_warning, log_error


class VideoFileManager:
    """Manages video file discovery, selection, and local caching"""

    SUPPORTED_EXTENSIONS = [
        ".mp4",
        ".avi",
        ".mov",
        ".mkv",
        ".wmv",
        ".flv",
        ".webm",
        ".m4v",
    ]

    def __init__(
        self,
        configured_file: str = "videos/sync_test.mp4",
        usb_mount_point: Optional[str] = None,
        cache_dir: Optional[str] = None,
    ):
        self.configured_file = configured_file
        self.usb_mount_point = usb_mount_point
        
        # Calculate project root (one level up from src/)
        # We also check the current working directory as a safety fallback
        try:
            self.project_root = Path(__file__).parent.parent.parent.resolve()
        except Exception:
            self.project_root = Path(os.getcwd()).resolve()
        
        # Prioritize absolute paths for stability
        self.fallback_sources = [
            str(self.project_root / "videos"),
            str(Path(os.getcwd()).resolve() / "videos"),
            str(self.project_root),
            str(Path(os.getcwd()).resolve()),
            "./videos",
            "."
        ]
        
        # Remove duplicates while preserving order
        seen = set()
        self.fallback_sources = [x for x in self.fallback_sources if not (x in seen or seen.add(x))]
        
        self.cache_dir = cache_dir or os.path.expanduser("~/kitchensync_cache")

    def find_video_file(self, target_file: Optional[str] = None, use_cache: bool = False) -> Optional[str]:
        """Find video file with intelligent fallback and optional caching"""
        search_log = []
        found_path = None
        
        # Use the provided target_file or fall back to the configured one
        file_to_find = target_file if target_file else self.configured_file

        # Step 1: Look for file on the specific USB mount point
        if self.usb_mount_point:
            usb_path = os.path.join(self.usb_mount_point, file_to_find)
            search_log.append(f"1. Specific USB path: {os.path.abspath(usb_path)}")
            if os.path.exists(usb_path):
                found_path = usb_path

        # Step 2: Look for file on all USB drives
        if not found_path:
            usb_mounts = self._get_usb_mount_points()
            if usb_mounts:
                for mount_point in usb_mounts:
                    usb_path = os.path.join(mount_point, file_to_find)
                    search_log.append(f"2. USB drive path: {os.path.abspath(usb_path)}")
                    if os.path.exists(usb_path):
                        found_path = usb_path
                        break
            else:
                search_log.append("2. No USB drives detected.")

        # Step 3: Look for file locally
        if not found_path:
            local_path = os.path.join(os.getcwd(), file_to_find)
            search_log.append(f"3. Local path: {local_path}")
            if os.path.exists(local_path):
                found_path = local_path

        # Step 4: Check local fallback directories
        if not found_path:
            for source in self.fallback_sources:
                fallback_path = os.path.join(source, file_to_find)
                search_log.append(f"4. Fallback directory: {os.path.abspath(fallback_path)}")
                if os.path.exists(fallback_path):
                    found_path = fallback_path
                    break

        # Step 5: Find any video file on the specific USB mount point (only if no target specified)
        if not found_path and not target_file and self.usb_mount_point:
            video_path = self._find_any_video_in_directory(self.usb_mount_point)
            search_log.append(
                f"5. Any video on specific USB: {os.path.abspath(self.usb_mount_point)}"
            )
            if video_path:
                found_path = video_path

        # Step 6: Find any video file on all USB drives (only if no target specified)
        if not found_path and not target_file:
            usb_mounts = self._get_usb_mount_points()
            if usb_mounts:
                for mount_point in usb_mounts:
                    video_path = self._find_any_video_in_directory(mount_point)
                    search_log.append(f"6. Any video on all USBs: {os.path.abspath(mount_point)}")
                    if video_path:
                        found_path = video_path
                        break

        # Step 7: Find any video file locally (only if no target specified)
        if not found_path and not target_file:
            for source in self.fallback_sources:
                video_path = self._find_any_video_in_directory(source)
                search_log.append(f"7. Any video in fallback source: {os.path.abspath(source)}")
                if video_path:
                    found_path = video_path
                    break

        if not found_path:
            log_error("Could not find any video file in search paths.", "video")
            for log in search_log:
                log_error(f"  Checked: {log}", "video")
            return None

        # Apply Caching if requested and file is external
        if use_cache and self._is_external_path(found_path):
            return self.cache_file(found_path)

        return found_path

    def cache_file(self, source_path: str) -> str:
        """Copy a file to local cache and return the local path"""
        try:
            if not os.path.exists(self.cache_dir):
                os.makedirs(self.cache_dir, exist_ok=True)

            filename = os.path.basename(source_path)
            cache_path = os.path.join(self.cache_dir, filename)

            # Check if cache is already valid (same size and mtime)
            if os.path.exists(cache_path):
                source_stat = os.stat(source_path)
                cache_stat = os.stat(cache_path)
                if (
                    source_stat.st_size == cache_stat.st_size
                    and abs(source_stat.st_mtime - cache_stat.st_mtime) < 1.0
                ):
                    log_info(f"Using cached file: {cache_path}", "video")
                    return cache_path

            # Copy file
            log_info(f"Caching file to local SD: {source_path} -> {cache_path}", "video")
            start_t = time.time()
            shutil.copy2(source_path, cache_path)
            duration = time.time() - start_t
            
            size_mb = os.path.getsize(cache_path) / (1024 * 1024)
            speed = size_mb / duration if duration > 0 else 0
            log_info(f"Cache complete: {size_mb:.1f} MB in {duration:.1f}s ({speed:.1f} MB/s)", "video")

            return cache_path
        except Exception as e:
            log_error(f"Failed to cache file: {e}", "video")
            return source_path

    def _is_external_path(self, path: str) -> bool:
        """Check if a path is on an external drive (USB)"""
        abs_path = os.path.abspath(path)
        return "/media/" in abs_path or "/mnt/" in abs_path

    def find_all_video_files(self) -> List[str]:
        """Find all available video files"""
        video_files = []

        # Check USB drives
        for mount_point in self._get_usb_mount_points():
            video_files.extend(self._get_videos_in_directory(mount_point))

        # Check local directories
        for source in self.fallback_sources:
            if os.path.exists(source):
                video_files.extend(self._get_videos_in_directory(source))

        return list(set(video_files))  # Remove duplicates

    def get_primary_video_dir(self) -> str:
        """Get the primary directory where videos should be stored/managed"""
        if self.usb_mount_point and os.path.exists(self.usb_mount_point):
            return self.usb_mount_point
        
        # Fallback to first existing local source
        for source in self.fallback_sources:
            if os.path.exists(source):
                return os.path.abspath(source)
        
        # Default to ./videos/
        os.makedirs("./videos", exist_ok=True)
        return os.path.abspath("./videos")

    def list_videos(self) -> List[dict]:
        """List all available video files with metadata"""
        video_files = []
        seen_names = set()

        log_info(f"Scanning for videos in fallback sources: {self.fallback_sources}", "video")

        # Check USB drives
        usb_mounts = self._get_usb_mount_points()
        for mount_point in usb_mounts:
            vids = self._get_videos_in_directory(mount_point)
            log_info(f"Found {len(vids)} videos on USB mount: {mount_point}", "video")
            for vid_path in vids:
                name = os.path.basename(vid_path)
                if name not in seen_names:
                    try:
                        stats = os.stat(vid_path)
                        video_files.append({
                            "name": name,
                            "path": vid_path,
                            "size": stats.st_size,
                            "mtime": stats.st_mtime,
                            "location": "usb"
                        })
                        seen_names.add(name)
                    except Exception as e:
                        log_error(f"Error reading video metadata for {vid_path}: {e}", "video")

        # Check local directories
        for source in self.fallback_sources:
            if os.path.exists(source):
                vids = self._get_videos_in_directory(source)
                log_info(f"Found {len(vids)} videos in local source: {source}", "video")
                for vid_path in vids:
                    name = os.path.basename(vid_path)
                    if name not in seen_names:
                        try:
                            stats = os.stat(vid_path)
                            video_files.append({
                                "name": name,
                                "path": os.path.abspath(vid_path),
                                "size": stats.st_size,
                                "mtime": stats.st_mtime,
                                "location": "local"
                            })
                            seen_names.add(name)
                        except Exception as e:
                            log_error(f"Error reading video metadata for {vid_path}: {e}", "video")
            else:
                log_warning(f"Local source directory does not exist: {source}", "video")

        return sorted(video_files, key=lambda x: x["name"])

    def delete_video(self, filename: str) -> bool:
        """Delete a video file by name from any discovered location"""
        deleted = False
        # Search all possible locations
        locations = self._get_usb_mount_points() + self.fallback_sources
        
        for loc in locations:
            if not os.path.exists(loc):
                continue
            
            target = os.path.join(loc, filename)
            if os.path.exists(target):
                try:
                    os.remove(target)
                    log_info(f"Deleted video: {target}", "video")
                    deleted = True
                except Exception as e:
                    log_error(f"Failed to delete {target}: {e}", "video")
        
        return deleted

    def _get_usb_mount_points(self) -> List[str]:
        """Get all USB mount points"""
        mount_points = []
        try:
            mount_result = subprocess.run(["mount"], capture_output=True, text=True)
            if mount_result.returncode == 0:
                for line in mount_result.stdout.split("\n"):
                    if "/media/" in line and (
                        "usb" in line.lower() or "sd" in line or "mmc" in line
                    ):
                        parts = line.split(" on ")
                        if len(parts) >= 2:
                            mount_point = parts[1].split(" type ")[0]
                            if os.path.exists(mount_point) and os.path.isdir(
                                mount_point
                            ):
                                mount_points.append(mount_point)
        except Exception as e:
            pass  # Ignore USB mount errors
        return mount_points

    def _find_any_video_in_directory(self, directory: str) -> Optional[str]:
        """Find any video file in a directory (case-insensitive)"""
        vids = self._get_videos_in_directory(directory)
        return vids[0] if vids else None

    def _get_videos_in_directory(self, directory: str) -> List[str]:
        """Get all video files in a directory (case-insensitive)"""
        if not os.path.exists(directory):
            return []

        videos = []
        try:
            # Get all files and filter manually for case-insensitivity
            all_files = os.listdir(directory)
            for filename in all_files:
                file_path = os.path.join(directory, filename)
                if os.path.isfile(file_path):
                    ext = os.path.splitext(filename)[1].lower()
                    if ext in self.SUPPORTED_EXTENSIONS:
                        videos.append(file_path)
        except Exception as e:
            log_error(f"Error scanning directory {directory}: {e}", "video")
            
        return videos

    @staticmethod
    def validate_video_file(video_path: str) -> bool:
        """Validate that a video file exists and is accessible"""
        if not video_path or not os.path.exists(video_path):
            return False

        try:
            # Check if file is readable
            with open(video_path, "rb") as f:
                f.read(1024)  # Try to read first 1KB
            return True
        except Exception:
            return False
