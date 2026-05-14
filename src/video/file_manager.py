#!/usr/bin/env python3
"""
Video File Discovery and Management for KitchenSync
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
        configured_file: str = "video.mp4",
        usb_mount_point: Optional[str] = None,
        cache_dir: Optional[str] = None,
    ):
        self.configured_file = configured_file
        self.usb_mount_point = usb_mount_point
        self.fallback_sources = ["./videos/", "./"]
        self.cache_dir = cache_dir or os.path.expanduser("~/kitchensync_cache")

    def find_video_file(self, use_cache: bool = False) -> Optional[str]:
        """Find video file with intelligent fallback and optional caching"""
        search_log = []
        found_path = None

        # Step 1: Look for configured file on the specific USB mount point
        if self.usb_mount_point:
            usb_path = os.path.join(self.usb_mount_point, self.configured_file)
            search_log.append(f"1. Specific USB path: {os.path.abspath(usb_path)}")
            if os.path.exists(usb_path):
                found_path = usb_path

        # Step 2: Look for configured file on all USB drives
        if not found_path:
            usb_mounts = self._get_usb_mount_points()
            if usb_mounts:
                for mount_point in usb_mounts:
                    usb_path = os.path.join(mount_point, self.configured_file)
                    search_log.append(f"2. USB drive configured file: {os.path.abspath(usb_path)}")
                    if os.path.exists(usb_path):
                        found_path = usb_path
                        break
            else:
                search_log.append("2. No USB drives detected.")

        # Step 3: Look for configured file locally
        if not found_path:
            local_path = os.path.join(os.getcwd(), self.configured_file)
            search_log.append(f"3. Local path: {local_path}")
            if os.path.exists(local_path):
                found_path = local_path

        # Step 4: Check local fallback directories
        if not found_path:
            for source in self.fallback_sources:
                fallback_path = os.path.join(source, self.configured_file)
                search_log.append(f"4. Fallback directory: {os.path.abspath(fallback_path)}")
                if os.path.exists(fallback_path):
                    found_path = fallback_path
                    break

        # Step 5: Find any video file on the specific USB mount point
        if not found_path and self.usb_mount_point:
            video_path = self._find_any_video_in_directory(self.usb_mount_point)
            search_log.append(
                f"5. Any video on specific USB: {os.path.abspath(self.usb_mount_point)}"
            )
            if video_path:
                found_path = video_path

        # Step 6: Find any video file on all USB drives
        if not found_path:
            usb_mounts = self._get_usb_mount_points()
            if usb_mounts:
                for mount_point in usb_mounts:
                    video_path = self._find_any_video_in_directory(mount_point)
                    search_log.append(f"6. Any video on all USBs: {os.path.abspath(mount_point)}")
                    if video_path:
                        found_path = video_path
                        break
            else:
                search_log.append("6. No USB drives to search for 'any' video.")

        # Step 7: Find any video file locally
        if not found_path:
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
        """Find any video file in a directory"""
        if not os.path.exists(directory):
            return None

        for ext in self.SUPPORTED_EXTENSIONS:
            videos = glob.glob(os.path.join(directory, f"*{ext}"))
            if videos:
                return videos[0]  # Return first found
        return None

    def _get_videos_in_directory(self, directory: str) -> List[str]:
        """Get all video files in a directory"""
        if not os.path.exists(directory):
            return []

        videos = []
        for ext in self.SUPPORTED_EXTENSIONS:
            videos.extend(glob.glob(os.path.join(directory, f"*{ext}")))
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
