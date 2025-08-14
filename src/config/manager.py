#!/usr/bin/env python3
"""
Configuration Management for KitchenSync
Handles loading and managing configuration from various sources
"""

import configparser
import os
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any

from src.core.logger import log_info, log_warning, log_error


class ConfigurationError(Exception):
    """Raised when configuration loading fails"""

    pass


class USBConfigLoader:
    """Handles USB drive configuration detection and loading"""

    @staticmethod
    def find_usb_mount_points() -> list[str]:
        """Find all mounted USB drives"""
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
            print(f"Error checking USB drives: {e}")
        return mount_points

    @staticmethod
    def find_config_on_usb() -> Optional[str]:
        """Find kitchensync.ini on USB drives"""
        for mount_point in USBConfigLoader.find_usb_mount_points():
            config_path = os.path.join(mount_point, "kitchensync.ini")
            if os.path.exists(config_path):
                return config_path
        return None

    @staticmethod
    def find_video_on_usb() -> Optional[Dict[str, str]]:
        """Find a video file on USB drives"""
        video_extensions = [".mp4", ".mov", ".mkv"]
        for mount_point in USBConfigLoader.find_usb_mount_points():
            for root, _, files in os.walk(mount_point):
                for file in files:
                    if any(file.lower().endswith(ext) for ext in video_extensions):
                        video_path = os.path.join(root, file)
                        log_info(
                            f"Found video on USB: {video_path}", component="config"
                        )
                        return {"mount_point": mount_point, "video_file": file}
        return None


class ConfigManager:
    """Central configuration manager for KitchenSync"""

    def __init__(self, config_file: Optional[str] = None):
        self.config = configparser.ConfigParser()
        self.config_file = config_file
        self.usb_config_path = None
        self._usb_mount_point = None  # Use a private attribute
        self.load_configuration()

    def load_configuration(self) -> None:
        """Load configuration from USB, file, or create defaults"""
        # Try USB first
        self.usb_config_path = USBConfigLoader.find_config_on_usb()
        if self.usb_config_path:
            self.config.read(self.usb_config_path)
            self._usb_mount_point = os.path.dirname(self.usb_config_path)
            log_info(
                f"Loaded config from USB: {self.usb_config_path}", component="config"
            )
            return

        # Try to find video on USB if no config is found
        usb_video_info = USBConfigLoader.find_video_on_usb()
        if usb_video_info:
            log_info(
                "No config file found, but a video was detected on USB.",
                component="config",
            )
            log_info(
                "Assuming 'collaborator' role and creating a default config.",
                component="config",
            )
            self._create_default_config(
                is_leader=False, video_file=usb_video_info["video_file"]
            )
            self._usb_mount_point = usb_video_info["mount_point"]
            return

        # Try specified config file
        if self.config_file and os.path.exists(self.config_file):
            self.config.read(self.config_file)
            log_info(f"Loaded config from: {self.config_file}", component="config")
            return

        # Create default configuration if no other option is available
        log_warning(
            "No config file or USB drive found. Creating default config.",
            component="config",
        )
        self._create_default_config()

    def _create_default_config(
        self, is_leader: bool = False, video_file: Optional[str] = None
    ) -> None:
        """Create default configuration"""
        self.config["KITCHENSYNC"] = {
            "is_leader": str(is_leader).lower(),
            "debug": "false",
            "device_id": f"pi-{int(os.urandom(2).hex(), 16):03d}",
            "video_file": video_file or "video.mp4",
            # Logging settings - default to minimal for performance
            "enable_vlc_logging": "false",
            "enable_system_logging": "false",
            "vlc_log_level": "0",  # 0=errors only, 1=warnings, 2=info, 3=debug
            # Networking / sync
            "tick_interval": "0.1",  # seconds between leader sync broadcasts
            # Audio output selection
            "audio_output": "hdmi",  # hdmi or headphone
        }

        if self.config_file and not os.path.exists(self.config_file):
            try:
                with open(self.config_file, "w") as f:
                    self.config.write(f)
                log_info(
                    f"Created default config file: {self.config_file}",
                    component="config",
                )
            except IOError as e:
                log_error(
                    f"Could not write default config file: {e}", component="config"
                )

    def get(self, key: str, default: Any = None, section: str = "KITCHENSYNC") -> Any:
        """Get configuration value"""
        try:
            if section in self.config:
                return self.config.get(section, key, fallback=default)
            elif "DEFAULT" in self.config:
                return self.config.get("DEFAULT", key, fallback=default)
            return default
        except Exception:
            return default

    def getboolean(
        self, key: str, default: bool = False, section: str = "KITCHENSYNC"
    ) -> bool:
        """Get boolean configuration value"""
        try:
            if section in self.config:
                return self.config.getboolean(section, key, fallback=default)
            elif "DEFAULT" in self.config:
                return self.config.getboolean("DEFAULT", key, fallback=default)
            return default
        except Exception:
            return default

    def getint(self, key: str, default: int = 0, section: str = "KITCHENSYNC") -> int:
        """Get integer configuration value"""
        try:
            if section in self.config:
                return self.config.getint(section, key, fallback=default)
            elif "DEFAULT" in self.config:
                return self.config.getint("DEFAULT", key, fallback=default)
            return default
        except Exception:
            return default

    def getfloat(
        self, key: str, default: float = 0.0, section: str = "KITCHENSYNC"
    ) -> float:
        """Get float configuration value"""
        try:
            if section in self.config:
                return self.config.getfloat(section, key, fallback=default)
            elif "DEFAULT" in self.config:
                return self.config.getfloat("DEFAULT", key, fallback=default)
            return default
        except Exception:
            return default

    def update_local_config(self, target_file: str, updates: Dict[str, Any]) -> None:
        """Update local configuration file with new values"""
        local_config = configparser.ConfigParser()

        # Load existing config or create new
        if os.path.exists(target_file):
            local_config.read(target_file)

        # Ensure DEFAULT section exists
        if "DEFAULT" not in local_config:
            local_config.add_section("DEFAULT")

        # Apply updates
        for key, value in updates.items():
            local_config.set("DEFAULT", key, str(value))

        # Save updated config
        with open(target_file, "w") as f:
            local_config.write(f)

        print(f"✓ Updated {target_file}")

    @property
    def is_leader(self) -> bool:
        """Check if this instance should run as leader"""
        return self.getboolean("is_leader", False)

    @property
    def debug_mode(self) -> bool:
        """Check if debug mode is enabled"""
        return self.getboolean("debug", False)

    @property
    def device_id(self) -> str:
        """Get device identifier"""
        return self.get("device_id", "unknown-pi")

    @property
    def video_file(self) -> str:
        """Get configured video file"""
        return self.get("video_file", "video.mp4")

    @property
    def usb_mount_point(self) -> Optional[str]:
        """Get USB mount point if available"""
        return self._usb_mount_point

    @property
    def enable_vlc_logging(self) -> bool:
        """Check if VLC detailed logging is enabled"""
        return self.getboolean("enable_vlc_logging", False)

    @property
    def enable_system_logging(self) -> bool:
        """Check if system detailed logging is enabled"""
        return self.getboolean("enable_system_logging", False)

    @property
    def vlc_log_level(self) -> int:
        """Get VLC logging verbosity level (0=errors, 1=warnings, 2=info, 3=debug)"""
        return self.getint("vlc_log_level", 0)

    @property
    def tick_interval(self) -> float:
        """Leader broadcast interval in seconds (default 0.1)."""
        return self.getfloat("tick_interval", 0.1)

    @property
    def audio_output(self) -> str:
        """Get audio output selection (hdmi or headphone, default: hdmi)."""
        return self.get("audio_output", "hdmi")
