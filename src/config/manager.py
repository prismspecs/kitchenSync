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

from core.logger import log_info, log_warning, log_error


CONFIG_ROLE_SECTIONS = {
    "leader": {
        "KITCHENSYNC": {"is_leader", "device_id", "debug", "enable_system_logging", "enable_audio", "audio_output", "enable_midi", "enable_osc", "enable_caching"},
        "DEFAULT": {"video_file", "schedule_file", "video_driver", "sync_port", "tick_interval", "max_drift", "min_drift", "kp", "min_rate", "max_rate", "max_samples"},
    },
    "collaborator": {
        "KITCHENSYNC": {"debug", "enable_system_logging", "enable_audio", "enable_caching"},
        "DEFAULT": {"device_id", "video_file", "video_driver", "midi_port", "sync_port"},
    },
}

EDITABLE_CONFIG_FIELDS = {
    "leader": [
        {"key": "video_file", "section": "DEFAULT", "type": "string", "label": "Video file", "default": "video.mp4"},
        {"key": "schedule_file", "section": "DEFAULT", "type": "string", "label": "Schedule file", "default": "schedule.json"},
        {"key": "enable_audio", "section": "KITCHENSYNC", "type": "bool", "label": "Enable Audio", "default": True},
        {"key": "audio_output", "section": "KITCHENSYNC", "type": "string", "label": "Audio Output", "default": "hdmi", "tooltip": "hdmi or headphone"},
        {"key": "enable_midi", "section": "KITCHENSYNC", "type": "bool", "label": "Enable MIDI", "default": True},
        {"key": "enable_caching", "section": "KITCHENSYNC", "type": "bool", "label": "Local Caching", "default": False, "tooltip": "Copy files from USB to local SD card before playback for better performance."},
        {"key": "debug", "section": "KITCHENSYNC", "type": "bool", "label": "Debug", "default": False},
        {"key": "tick_interval", "section": "DEFAULT", "type": "float", "label": "Sync Interval", "default": 0.1, "tooltip": "How often the leader sends sync packets (in seconds). Smaller is faster but uses more network/CPU."},
        {"key": "max_drift", "section": "DEFAULT", "type": "float", "label": "Max Drift", "default": 0.5, "tooltip": "Threshold (in seconds) for a hard seek. If the node is further away than this, it jumps to the leader time."},
        {"key": "min_drift", "section": "DEFAULT", "type": "float", "label": "Min Drift", "default": 0.01, "tooltip": "Threshold (in seconds) where speed adjustment begins. Drifts smaller than this are ignored for stability."},
        {"key": "kp", "section": "DEFAULT", "type": "float", "label": "P-Gain", "default": 0.1, "tooltip": "The aggression of the speed correction. Higher values react faster but may cause visible speed jitter."},
        {"key": "max_samples", "section": "DEFAULT", "type": "int", "label": "Max Samples", "default": 5, "tooltip": "Number of samples for drift averaging. Lower values react faster; higher values are smoother but add lag."},
        {"key": "min_rate", "section": "DEFAULT", "type": "float", "label": "Min Rate", "default": 0.9, "tooltip": "Minimum playback speed adjustment (e.g. 0.9 = 90% speed)."},
        {"key": "max_rate", "section": "DEFAULT", "type": "float", "label": "Max Rate", "default": 1.2, "tooltip": "Maximum playback speed adjustment (e.g. 1.2 = 120% speed)."},
        {"key": "enable_system_logging", "section": "KITCHENSYNC", "type": "bool", "label": "Verbose logging", "default": False},
    ],
    "collaborator": [
        {"key": "video_file", "section": "DEFAULT", "type": "string", "label": "Video file", "default": "video.mp4"},
        {"key": "enable_audio", "section": "KITCHENSYNC", "type": "bool", "label": "Enable Audio", "default": True},
        {"key": "midi_port", "section": "DEFAULT", "type": "int", "label": "MIDI port", "default": 0},
        {"key": "debug", "section": "KITCHENSYNC", "type": "bool", "label": "Debug", "default": False},
    ],
}

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

    @staticmethod
    def find_schedule_on_usb() -> Optional[str]:
        """Find a MIDI schedule file on USB drives"""
        schedule_files = ["schedule.json", "midi_schedule.json", "relay_schedule.json"]
        for mount_point in USBConfigLoader.find_usb_mount_points():
            # Check root directory first
            for schedule_file in schedule_files:
                schedule_path = os.path.join(mount_point, schedule_file)
                if os.path.exists(schedule_path):
                    log_info(
                        f"Found schedule on USB: {schedule_path}", component="config"
                    )
                    return schedule_path

            # Check subdirectories for schedule files
            for root, _, files in os.walk(mount_point):
                for file in files:
                    if file.lower() in [sf.lower() for sf in schedule_files]:
                        schedule_path = os.path.join(root, file)
                        log_info(
                            f"Found schedule on USB: {schedule_path}",
                            component="config",
                        )
                        return schedule_path
        return None

    @staticmethod
    def find_midi_file_on_usb() -> Optional[str]:
        """Find a MIDI file on USB drives for conversion to schedule"""
        midi_extensions = [".mid", ".midi"]
        for mount_point in USBConfigLoader.find_usb_mount_points():
            for root, _, files in os.walk(mount_point):
                for file in files:
                    if any(file.lower().endswith(ext) for ext in midi_extensions):
                        midi_path = os.path.join(root, file)
                        log_info(
                            f"Found MIDI file on USB: {midi_path}", component="config"
                        )
                        return midi_path
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
            "video_driver": "gst",
            # Logging settings - default to minimal for performance
            "enable_system_logging": "false",
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

        print(f" Updated {target_file}")

    def role_name(self) -> str:
        """Return the runtime role associated with this config."""
        return "leader" if self.is_leader else "collaborator"

    def get_config_path(self) -> Optional[str]:
        """Return the active writable config path."""
        if self.config_file:
            return self.config_file
        return self.usb_config_path

    def get_editable_fields(self, role: Optional[str] = None) -> list[Dict[str, Any]]:
        """Return metadata for fields exposed in the remote controller."""
        return list(EDITABLE_CONFIG_FIELDS[self._normalize_role(role)])

    def get_editable_values(self, role: Optional[str] = None) -> Dict[str, Any]:
        """Return editable config values using native Python types."""
        values: Dict[str, Any] = {}
        for field in self.get_editable_fields(role):
            key = field["key"]
            section = field["section"]
            field_type = field["type"]
            default = field.get("default")
            if field_type == "int":
                values[key] = self.getint(key, int(default) if default is not None else 0, section=section)
            elif field_type == "float":
                values[key] = self.getfloat(key, float(default) if default is not None else 0.0, section=section)
            elif field_type == "bool":
                values[key] = self.getboolean(key, bool(default) if default is not None else False, section=section)
            else:
                values[key] = self.get(key, str(default) if default is not None else "", section=section)
        return values

    def get_default_values(self, role: Optional[str] = None) -> Dict[str, Any]:
        """Return the default values for editable fields."""
        values: Dict[str, Any] = {}
        for field in self.get_editable_fields(role):
            values[field["key"]] = field.get("default")
        return values

    def clean_and_save_config(
        self,
        target_file: str,
        updates: Dict[str, Any],
        role: Optional[str] = None,
    ) -> None:
        """Rewrite a config file to the supported surface for the given role."""
        role_name = self._normalize_role(role)
        existing = configparser.ConfigParser()
        if os.path.exists(target_file):
            existing.read(target_file)

        cleaned = configparser.ConfigParser()
        cleaned["KITCHENSYNC"] = {}
        cleaned["DEFAULT"] = {}

        for section_name, keys in CONFIG_ROLE_SECTIONS[role_name].items():
            for key in sorted(keys):
                value = self._resolve_config_value(existing, updates, section_name, key)
                if value is None:
                    continue
                cleaned[section_name][key] = self._stringify_config_value(value)

        with open(target_file, "w") as handle:
            cleaned.write(handle)

        if self.get_config_path() == target_file:
            self.config = cleaned

    def _normalize_role(self, role: Optional[str]) -> str:
        resolved = role or self.role_name()
        if resolved not in CONFIG_ROLE_SECTIONS:
            raise ConfigurationError(f"Unsupported config role: {resolved}")
        return resolved

    def _resolve_config_value(
        self,
        parser: configparser.ConfigParser,
        updates: Dict[str, Any],
        section: str,
        key: str,
    ) -> Any:
        if key in updates:
            return updates[key]

        if section != "DEFAULT" and section in parser and key in parser[section]:
            return parser[section][key]

        if key in parser.defaults():
            return parser.defaults()[key]

        if section != "DEFAULT" and section in self.config and key in self.config[section]:
            return self.config[section][key]

        if key in self.config.defaults():
            return self.config.defaults()[key]

        return None

    @staticmethod
    def _stringify_config_value(value: Any) -> str:
        if isinstance(value, bool):
            return str(value).lower()
        return str(value)

    @property
    def content_dir(self) -> str:
        """Get the directory where content (video/schedules) is located"""
        if self._usb_mount_point:
            return self._usb_mount_point
        return os.getcwd()

    @property
    def schedule_file(self) -> str:
        """Get the path to the schedule JSON file"""
        # Try to find on USB first
        usb_schedule = USBConfigLoader.find_schedule_on_usb()
        if usb_schedule:
            return usb_schedule
        
        # Fallback to config value or default
        return self.get("schedule_file", "schedule.json")

    @property
    def video_driver(self) -> str:
        """Get selected video driver (gstreamer or mock)."""
        return self.get("video_driver", "gst")

    @property
    def enable_midi(self) -> bool:
        """Check if MIDI output is enabled"""
        return self.getboolean("enable_midi", True)

    @property
    def enable_osc(self) -> bool:
        """Check if OSC output is enabled"""
        return self.getboolean("enable_osc", False)

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
    def enable_system_logging(self) -> bool:
        """Check if system detailed logging is enabled"""
        return self.getboolean("enable_system_logging", False)
        {
            "key": "enable_audio",
            "section": "KITCHENSYNC",
            "type": "bool",
            "label": "Enable Audio",
        },
        {
            "key": "tick_interval",
            "section": "DEFAULT",
            "type": "float",
            "label": "Sync Tick Interval",
        },
        {
            "key": "max_drift",
            "section": "DEFAULT",
            "type": "float",
            "label": "Max Drift (Hard Seek)",
        },
        {
            "key": "min_drift",
            "section": "DEFAULT",
            "type": "float",
            "label": "Min Drift (Fine Sync)",
        },
        {
            "key": "kp",
            "section": "DEFAULT",
            "type": "float",
            "label": "Sync P-Gain",
        },

    @property
    def tick_interval(self) -> float:
        """Leader broadcast interval in seconds (default 0.1)."""
        return self.getfloat("tick_interval", 0.1)

    @property
    def audio_output(self) -> str:
        """Get audio output selection (hdmi or headphone, default: hdmi)."""
        return self.get("audio_output", "hdmi")

    @property
    def max_drift(self) -> float:
        """Threshold for hard seek in seconds (default 0.5)."""
        return self.getfloat("max_drift", 0.5)

    @property
    def min_drift(self) -> float:
        """Threshold for fine speed adjustment in seconds (default 0.01)."""
        return self.getfloat("min_drift", 0.01)

    @property
    def kp(self) -> float:
        """P-gain coefficient for speed adjustment (default 0.1)."""
        return self.getfloat("kp", 0.1)

    @property
    def min_rate(self) -> float:
        """Minimum playback rate (default 0.9)."""
        return self.getfloat("min_rate", 0.9)

    @property
    def max_rate(self) -> float:
        """Maximum playback rate (default 1.2)."""
        return self.getfloat("max_rate", 1.2)

    @property
    def max_samples(self) -> int:
        """Number of samples for drift averaging (default 5)."""
        return self.getint("max_samples", 5)

    @property
    def enable_audio(self) -> bool:
        """Check if audio playback is enabled (default: True)."""
        return self.getboolean("enable_audio", True)

    @property
    def enable_caching(self) -> bool:
        """Check if local content caching is enabled (default: False)."""
        return self.getboolean("enable_caching", False)
