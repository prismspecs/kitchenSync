#!/usr/bin/env python3
"""
Video File Discovery and Management for KitchenSync
Handles finding and managing video files from various sources
"""

import glob
import os
import subprocess
from pathlib import Path
from typing import Optional, List

from src.core.logger import log_info, log_warning, log_error


class VideoFileManager:
    """Manages video file discovery and selection"""

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
        self, configured_file: str = "video.mp4", usb_mount_point: Optional[str] = None
    ):
        self.configured_file = configured_file
        self.usb_mount_point = usb_mount_point
        self.fallback_sources = ["./videos/", "./"]

    def find_video_file(self) -> Optional[str]:
        """Find video file with intelligent fallback logic"""
        search_log = []

        # Step 1: Look for configured file on the specific USB mount point
        if self.usb_mount_point:
            usb_path = os.path.join(self.usb_mount_point, self.configured_file)
            search_log.append(f"Searching specific USB path: {usb_path}")
            if os.path.exists(usb_path):
                log_info(f"Found video at specific USB path: {usb_path}", "video")
                return usb_path

        # Step 2: Look for configured file on all USB drives
        for mount_point in self._get_usb_mount_points():
            usb_path = os.path.join(mount_point, self.configured_file)
            search_log.append(f"Searching all USBs for configured file: {usb_path}")
            if os.path.exists(usb_path):
                log_info(f"Found configured video on USB drive: {usb_path}", "video")
                return usb_path

        # Step 3: Look for configured file locally
        local_path = self.configured_file
        search_log.append(f"Searching for configured file locally: {local_path}")
        if os.path.exists(local_path):
            log_info(f"Found configured video locally: {local_path}", "video")
            return local_path

        # Step 4: Check local fallback directories
        for source in self.fallback_sources:
            fallback_path = os.path.join(source, self.configured_file)
            search_log.append(f"Searching fallback directory: {fallback_path}")
            if os.path.exists(fallback_path):
                log_info(
                    f"Found configured video in fallback source: {fallback_path}",
                    "video",
                )
                return fallback_path

        # Step 5: Find any video file on the specific USB mount point
        if self.usb_mount_point:
            video_path = self._find_any_video_in_directory(self.usb_mount_point)
            search_log.append(
                f"Searching for any video on specific USB: {self.usb_mount_point}"
            )
            if video_path:
                log_info(f"Found any video on specific USB: {video_path}", "video")
                return video_path

        # Step 6: Find any video file on all USB drives
        for mount_point in self._get_usb_mount_points():
            video_path = self._find_any_video_in_directory(mount_point)
            search_log.append(f"Searching for any video on all USBs: {mount_point}")
            if video_path:
                log_info(f"Found any video on a USB drive: {video_path}", "video")
                return video_path

        # Step 7: Find any video file locally
        for source in self.fallback_sources:
            video_path = self._find_any_video_in_directory(source)
            search_log.append(f"Searching for any video in fallback source: {source}")
            if video_path:
                log_info(f"Found any video in fallback source: {video_path}", "video")
                return video_path

        log_warning("Could not find any video file.", "video")
        log_info(f"Search log: {search_log}", "video")
        return None

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
