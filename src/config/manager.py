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
        "KITCHENSYNC": {"role", "device_id", "debug", "enable_system_logging", "enable_audio", "audio_output", "enable_midi", "enable_osc", "enable_caching", "enable_latency_compensation"},
        "DEFAULT": {"video_file", "schedule_file", "video_driver", "sync_port", "tick_interval", "latency_factor", "max_drift", "min_drift", "kp", "min_rate", "max_rate", "max_samples"},
    },
    "collaborator": {
        "KITCHENSYNC": {"role", "debug", "enable_system_logging", "enable_audio", "enable_caching"},
        "DEFAULT": {"device_id", "video_file", "video_driver", "midi_port", "sync_port"},
    },
    "bystander": {
        "KITCHENSYNC": {"role", "device_id", "debug", "enable_system_logging"},
        "DEFAULT": {},
    },
}

EDITABLE_CONFIG_FIELDS = {
    "leader": [
        {"key": "role", "section": "KITCHENSYNC", "type": "choice", "label": "Role", "default": "leader", "options": ["leader", "collaborator", "bystander"], "tooltip": "Leader: Master clock and media server. Collaborator: Syncs to leader. Bystander: Idle, waits for provisioning."},
        {"key": "video_file", "section": "DEFAULT", "type": "string", "label": "Video file", "default": "videos/sync_test.mp4", "tooltip": "The video file to play. Searches USB first, then local videos/ folder."},
        {"key": "schedule_file", "section": "DEFAULT", "type": "string", "label": "Schedule file", "default": "schedule.json", "tooltip": "MIDI/OSC cue schedule file (.json or .mid)."},
        {"key": "enable_audio", "section": "KITCHENSYNC", "type": "bool", "label": "Enable Audio", "default": True, "tooltip": "Toggle audio playback on/off."},
        {"key": "audio_output", "section": "KITCHENSYNC", "type": "choice", "label": "Audio Output", "default": "hdmi", "options": ["hdmi", "headphone"], "tooltip": "Select audio destination: HDMI or the 3.5mm Headphone Jack."},
        {"key": "enable_midi", "section": "KITCHENSYNC", "type": "bool", "label": "Enable MIDI", "default": True, "tooltip": "Enable MIDI output triggers via USB or Serial."},
        {"key": "enable_caching", "section": "KITCHENSYNC", "type": "bool", "label": "Local Caching", "default": False, "tooltip": "If enabled, external USB videos will be copied to SD card for smoother playback."},
        {"key": "debug", "section": "KITCHENSYNC", "type": "bool", "label": "Debug", "default": False, "tooltip": "Enable on-screen debug overlay with sync stats."},
        {"key": "tick_interval", "section": "DEFAULT", "type": "float", "label": "Sync Interval", "default": 0.05, "tooltip": "How often (seconds) to broadcast time sync messages. Lower = tighter sync but more network traffic."},
        {"key": "enable_latency_compensation", "section": "KITCHENSYNC", "type": "bool", "label": "Latency Compensation", "default": True, "tooltip": "Automatically adjust for network RTT delay."},
        {"key": "latency_factor", "section": "DEFAULT", "type": "float", "label": "Latency Factor", "default": 0.5, "tooltip": "Weighting for RTT compensation (0.0 to 1.0)."},
        {"key": "max_drift", "section": "DEFAULT", "type": "float", "label": "Max Drift", "default": 0.5, "tooltip": "Maximum allowed sync deviation before a hard seek (jump) is forced."},
        {"key": "min_drift", "section": "DEFAULT", "type": "float", "label": "Min Drift", "default": 0.04, "tooltip": "Minimum deviation to ignore (prevents jitter)."},
        {"key": "kp", "section": "DEFAULT", "type": "float", "label": "P-Gain", "default": 0.15, "tooltip": "Proportional gain for playback speed adjustment. Higher = faster catchup."},
        {"key": "max_samples", "section": "DEFAULT", "type": "int", "label": "Max Samples", "default": 10, "tooltip": "Number of sync samples to average for drift calculation."},
        {"key": "min_rate", "section": "DEFAULT", "type": "float", "label": "Min Rate", "default": 0.9, "tooltip": "Minimum playback speed allowed for slow-down correction."},
        {"key": "max_rate", "section": "DEFAULT", "type": "float", "label": "Max Rate", "default": 1.2, "tooltip": "Maximum playback speed allowed for catch-up correction."},
        {"key": "enable_system_logging", "section": "KITCHENSYNC", "type": "bool", "label": "Verbose logging", "default": False, "tooltip": "Enable detailed logging to kitchensync.log for troubleshooting."},
    ],
    "collaborator": [
        {"key": "role", "section": "KITCHENSYNC", "type": "choice", "label": "Role", "default": "collaborator", "options": ["leader", "collaborator", "bystander"], "tooltip": "Leader: Master clock and media server. Collaborator: Syncs to leader. Bystander: Idle, waits for provisioning."},
        {"key": "video_file", "section": "DEFAULT", "type": "string", "label": "Video file", "default": "videos/sync_test.mp4", "tooltip": "Local video file to play when sync starts."},
        {"key": "enable_audio", "section": "KITCHENSYNC", "type": "bool", "label": "Enable Audio", "default": True, "tooltip": "Toggle audio playback on/off."},
        {"key": "audio_output", "section": "KITCHENSYNC", "type": "choice", "label": "Audio Output", "default": "hdmi", "options": ["hdmi", "headphone"], "tooltip": "Select audio destination: HDMI or the 3.5mm Headphone Jack."},
        {"key": "midi_port", "section": "DEFAULT", "type": "int", "label": "MIDI port", "default": 0, "tooltip": "The index of the MIDI output port to use."},
        {"key": "debug", "section": "KITCHENSYNC", "type": "bool", "label": "Debug", "default": False, "tooltip": "Enable on-screen debug overlay with sync stats."},
    ],
    "bystander": [
        {"key": "role", "section": "KITCHENSYNC", "type": "choice", "label": "Role", "default": "bystander", "options": ["leader", "collaborator", "bystander"], "tooltip": "Leader: Master clock and media server. Collaborator: Syncs to leader. Bystander: Idle, waits for provisioning."},
        {"key": "debug", "section": "KITCHENSYNC", "type": "bool", "label": "Debug", "default": False, "tooltip": "Enable on-screen debug overlay with sync stats."},
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
                            if os.path.exists(mount_point) and os.path.isdir(mount_point):
                                mount_points.append(mount_point)
        except Exception as e:
            print(f"Error checking USB drives: {e}")
        return mount_points

    @staticmethod
    def find_config_on_usb() -> Optional[str]:
        """Find ksync.ini on USB drives, prioritizing root."""
        mount_points = USBConfigLoader.find_usb_mount_points()
        # Prioritize root
        for mount_point in mount_points:
            config_path = os.path.join(mount_point, "ksync.ini")
            if os.path.exists(config_path):
                return config_path
        # Then subdirs
        for mount_point in mount_points:
            for root, _, files in os.walk(mount_point):
                if "ksync.ini" in files:
                    return os.path.join(root, "ksync.ini")
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
                        log_info(f"Found video on USB: {video_path}", component="config")
                        return {"mount_point": mount_point, "video_file": file}
        return None

    @staticmethod
    def find_schedule_on_usb() -> Optional[str]:
        """Find a MIDI schedule file on USB drives"""
        schedule_files = ["schedule.json", "midi_schedule.json", "relay_schedule.json"]
        for mount_point in USBConfigLoader.find_usb_mount_points():
            for root, _, files in os.walk(mount_point):
                for file in files:
                    if file.lower() in [sf.lower() for sf in schedule_files]:
                        schedule_path = os.path.join(root, file)
                        log_info(f"Found schedule on USB: {schedule_path}", component="config")
                        return schedule_path
        return None


class ConfigManager:
    """Central configuration manager for KitchenSync"""

    def __init__(self, config_file: Optional[str] = None):
        self.config = configparser.ConfigParser()
        self.config_file = config_file
        self.usb_config_path = None
        self._usb_mount_point = None
        self.load_configuration()

    def load_configuration(self) -> None:
        """Load configuration from USB, file, or create defaults"""
        # 1. Try USB prioritize root (via USBConfigLoader)
        self.usb_config_path = USBConfigLoader.find_config_on_usb()
        if self.usb_config_path:
            self.config.read(self.usb_config_path)
            self._usb_mount_point = os.path.dirname(self.usb_config_path)
            log_info(f"Loaded config from USB: {self.usb_config_path}", component="config")
            return

        # 2. Try specified config file
        if self.config_file and os.path.exists(self.config_file):
            self.config.read(self.config_file)
            log_info(f"Loaded config from: {self.config_file}", component="config")
            return

        # 3. Try finding video on USB to auto-configure as collaborator
        usb_video_info = USBConfigLoader.find_video_on_usb()
        if usb_video_info:
            log_info("No ksync.ini found, but video detected on USB. Auto-configuring collaborator.", component="config")
            self._create_default_config(role="collaborator", video_file=usb_video_info["video_file"])
            self._usb_mount_point = usb_video_info["mount_point"]
            return

        # 4. Fallback to bystander
        log_warning("No config file or USB found. Entering bystander mode.", component="config")
        self._create_default_config(role="bystander")

    def _create_default_config(self, role: str = "bystander", video_file: Optional[str] = None) -> None:
        """Create default configuration"""
        self.config["KITCHENSYNC"] = {
            "role": role,
            "debug": "false",
            "device_id": f"pi-{int(os.urandom(2).hex(), 16):03d}",
            "video_file": video_file or "video.mp4",
            "video_driver": "gst",
            "enable_system_logging": "false",
            "tick_interval": "0.1",
            "audio_output": "hdmi",
        }

        if self.config_file and not os.path.exists(self.config_file):
            try:
                with open(self.config_file, "w") as f:
                    self.config.write(f)
                log_info(f"Created default config file: {self.config_file}", component="config")
            except IOError as e:
                log_error(f"Could not write default config file: {e}", component="config")

    def get(self, key: str, default: Any = None, section: str = "KITCHENSYNC") -> Any:
        try:
            if section in self.config and key in self.config[section]:
                return self.config.get(section, key)
            if "DEFAULT" in self.config and key in self.config["DEFAULT"]:
                return self.config.get("DEFAULT", key)
            return default
        except Exception:
            return default

    def getboolean(self, key: str, default: bool = False, section: str = "KITCHENSYNC") -> bool:
        val = self.get(key, None, section)
        if val is None: return default
        return str(val).lower() in ("true", "yes", "1", "on")

    def getint(self, key: str, default: int = 0, section: str = "KITCHENSYNC") -> int:
        try: return int(self.get(key, default, section))
        except: return default

    def getfloat(self, key: str, default: float = 0.0, section: str = "KITCHENSYNC") -> float:
        try: return float(self.get(key, default, section))
        except: return default

    def update_local_config(self, target_file: str, updates: Dict[str, Any], section: str = "KITCHENSYNC") -> None:
        local_config = configparser.ConfigParser()
        if os.path.exists(target_file):
            local_config.read(target_file)
        if section not in local_config:
            local_config.add_section(section)
        for key, value in updates.items():
            local_config.set(section, key, str(value))
        with open(target_file, "w") as f:
            local_config.write(f)
        log_info(f"Updated {target_file}", component="config")

    @property
    def is_leader(self) -> bool:
        return self.get("role", "bystander").lower() == "leader"

    @property
    def is_bystander(self) -> bool:
        return self.get("role", "bystander").lower() == "bystander"

    def role_name(self) -> str:
        if self.is_leader: return "leader"
        if self.is_bystander: return "bystander"
        return "collaborator"

    def get_config_path(self) -> Optional[str]:
        return self.config_file or self.usb_config_path

    def get_editable_fields(self, role: Optional[str] = None) -> list[Dict[str, Any]]:
        return list(EDITABLE_CONFIG_FIELDS[role or self.role_name()])

    def get_editable_values(self, role: Optional[str] = None) -> Dict[str, Any]:
        values: Dict[str, Any] = {}
        for field in self.get_editable_fields(role):
            key = field["key"]
            section = field["section"]
            ftype = field["type"]
            default = field.get("default")
            if ftype == "int": values[key] = self.getint(key, int(default) if default is not None else 0, section)
            elif ftype == "float": values[key] = self.getfloat(key, float(default) if default is not None else 0.0, section)
            elif ftype == "bool": values[key] = self.getboolean(key, bool(default) if default is not None else False, section)
            else: values[key] = self.get(key, str(default) if default is not None else "", section)
        return values

    def get_default_values(self, role: Optional[str] = None) -> Dict[str, Any]:
        return {f["key"]: f.get("default") for f in self.get_editable_fields(role)}

    def clean_and_save_config(self, target_file: str, updates: Dict[str, Any], role: Optional[str] = None) -> None:
        role_name = role or self.role_name()
        cleaned = configparser.ConfigParser()
        cleaned["KITCHENSYNC"] = {}
        cleaned["DEFAULT"] = {}
        
        # Determine if we are updating the current config
        is_current = (self.get_config_path() == target_file)

        for sec, keys in CONFIG_ROLE_SECTIONS[role_name].items():
            if sec not in cleaned: cleaned.add_section(sec)
            for k in sorted(keys):
                val = updates.get(k)
                if val is None:
                    # Fallback to current
                    val = self.get(k, None, sec)
                if val is not None:
                    cleaned[sec][k] = str(val).lower() if isinstance(val, bool) else str(val)

        with open(target_file, "w") as handle:
            cleaned.write(handle)
        
        if is_current:
            self.config = cleaned

    def set_param(self, key: str, value: Any) -> None:
        # Live update internal object
        section = "KITCHENSYNC"
        for field in EDITABLE_CONFIG_FIELDS["leader"]:
            if field["key"] == key:
                section = field["section"]
                break
        if section not in self.config: self.config[section] = {}
        self.config[section][key] = str(value).lower() if isinstance(value, bool) else str(value)

    @property
    def content_dir(self) -> str:
        return self._usb_mount_point or os.getcwd()

    @property
    def video_file(self) -> str: return self.get("video_file", "video.mp4")

    @property
    def schedule_file(self) -> str:
        usb_sched = USBConfigLoader.find_schedule_on_usb()
        return usb_sched or self.get("schedule_file", "schedule.json")

    @property
    def video_driver(self) -> str: return self.get("video_driver", "gst")

    @property
    def enable_midi(self) -> bool: return self.getboolean("enable_midi", True)

    @property
    def enable_osc(self) -> bool: return self.getboolean("enable_osc", False)

    @property
    def debug_mode(self) -> bool: return self.getboolean("debug", False)

    @property
    def device_id(self) -> str:
        cid = self.get("device_id", "pi-unknown")
        if cid in ["pi-unknown", "pi-001", "unknown-pi"]:
            hwid = self._get_hardware_id()
            if hwid: return f"pi-{hwid}"
        return cid

    def _get_hardware_id(self) -> Optional[str]:
        try:
            with open("/proc/cpuinfo", "r") as f:
                for line in f:
                    if line.startswith("Serial"):
                        s = line.split(":")[1].strip()
                        if s and s != "0000000000000000": return s[-6:]
        except: pass
        try:
            import uuid
            m = hex(uuid.getnode())[2:]
            if m: return m[-6:]
        except: pass
        return None

    @property
    def usb_mount_point(self) -> Optional[str]: return self._usb_mount_point

    @property
    def enable_system_logging(self) -> bool: return self.getboolean("enable_system_logging", False)

    @property
    def tick_interval(self) -> float: return self.getfloat("tick_interval", 0.1)

    @property
    def audio_output(self) -> str: return self.get("audio_output", "hdmi")

    @property
    def max_drift(self) -> float: return self.getfloat("max_drift", 0.5)

    @property
    def min_drift(self) -> float: return self.getfloat("min_drift", 0.01)

    @property
    def kp(self) -> float: return self.getfloat("kp", 0.25)

    @property
    def min_rate(self) -> float: return self.getfloat("min_rate", 0.9)

    @property
    def max_rate(self) -> float: return self.getfloat("max_rate", 1.2)

    @property
    def max_samples(self) -> int: return self.getint("max_samples", 10)

    @property
    def enable_audio(self) -> bool: return self.getboolean("enable_audio", True)

    @property
    def enable_latency_compensation(self) -> bool: return self.getboolean("enable_latency_compensation", True)

    @property
    def latency_factor(self) -> float: return self.getfloat("latency_factor", 0.5)

    @property
    def enable_caching(self) -> bool: return self.getboolean("enable_caching", False)
