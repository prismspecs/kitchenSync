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
            mount_result = subprocess.run(['mount'], capture_output=True, text=True)
            if mount_result.returncode == 0:
                for line in mount_result.stdout.split('\n'):
                    if '/media/' in line and ('usb' in line.lower() or 'sd' in line or 'mmc' in line):
                        parts = line.split(' on ')
                        if len(parts) >= 2:
                            mount_point = parts[1].split(' type ')[0]
                            if os.path.exists(mount_point) and os.path.isdir(mount_point):
                                mount_points.append(mount_point)
        except Exception as e:
            print(f"Error checking USB drives: {e}")
        return mount_points
    
    @staticmethod
    def find_config_on_usb() -> Optional[str]:
        """Find kitchensync.ini on USB drives"""
        for mount_point in USBConfigLoader.find_usb_mount_points():
            config_path = os.path.join(mount_point, 'kitchensync.ini')
            if os.path.exists(config_path):
                return config_path
        return None


class ConfigManager:
    """Central configuration manager for KitchenSync"""
    
    def __init__(self, config_file: Optional[str] = None):
        self.config = configparser.ConfigParser()
        self.config_file = config_file
        self.usb_config_path = None
        self.load_configuration()
    
    def load_configuration(self) -> None:
        """Load configuration from USB, file, or create defaults"""
        # Try USB first
        self.usb_config_path = USBConfigLoader.find_config_on_usb()
        if self.usb_config_path:
            self.config.read(self.usb_config_path)
            print(f"✓ Loaded config from USB: {self.usb_config_path}")
            return
        
        # Try specified config file
        if self.config_file and os.path.exists(self.config_file):
            self.config.read(self.config_file)
            print(f"✓ Loaded config from: {self.config_file}")
            return
        
        # Create default configuration
        self._create_default_config()
    
    def _create_default_config(self) -> None:
        """Create default configuration"""
        self.config['KITCHENSYNC'] = {
            'is_leader': 'false',
            'debug': 'false',
            'pi_id': f'pi-{int(os.urandom(2).hex(), 16):03d}'
        }
        
        if self.config_file:
            with open(self.config_file, 'w') as f:
                self.config.write(f)
            print(f"✓ Created default config: {self.config_file}")
    
    def get(self, key: str, default: Any = None, section: str = 'KITCHENSYNC') -> Any:
        """Get configuration value"""
        try:
            if section in self.config:
                return self.config.get(section, key, fallback=default)
            elif 'DEFAULT' in self.config:
                return self.config.get('DEFAULT', key, fallback=default)
            return default
        except Exception:
            return default
    
    def getboolean(self, key: str, default: bool = False, section: str = 'KITCHENSYNC') -> bool:
        """Get boolean configuration value"""
        try:
            if section in self.config:
                return self.config.getboolean(section, key, fallback=default)
            elif 'DEFAULT' in self.config:
                return self.config.getboolean('DEFAULT', key, fallback=default)
            return default
        except Exception:
            return default
    
    def getint(self, key: str, default: int = 0, section: str = 'KITCHENSYNC') -> int:
        """Get integer configuration value"""
        try:
            if section in self.config:
                return self.config.getint(section, key, fallback=default)
            elif 'DEFAULT' in self.config:
                return self.config.getint('DEFAULT', key, fallback=default)
            return default
        except Exception:
            return default
    
    def getfloat(self, key: str, default: float = 0.0, section: str = 'KITCHENSYNC') -> float:
        """Get float configuration value"""
        try:
            if section in self.config:
                return self.config.getfloat(section, key, fallback=default)
            elif 'DEFAULT' in self.config:
                return self.config.getfloat('DEFAULT', key, fallback=default)
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
        if 'DEFAULT' not in local_config:
            local_config.add_section('DEFAULT')
        
        # Apply updates
        for key, value in updates.items():
            local_config.set('DEFAULT', key, str(value))
        
        # Save updated config
        with open(target_file, 'w') as f:
            local_config.write(f)
        
        print(f"✓ Updated {target_file}")
    
    @property
    def is_leader(self) -> bool:
        """Check if this instance should run as leader"""
        return self.getboolean('is_leader', False)
    
    @property
    def debug_mode(self) -> bool:
        """Check if debug mode is enabled"""
        return self.getboolean('debug', False)
    
    @property
    def pi_id(self) -> str:
        """Get Pi identifier"""
        return self.get('pi_id', 'unknown-pi')
    
    @property
    def video_file(self) -> str:
        """Get configured video file"""
        return self.get('video_file', 'video.mp4')
    
    @property
    def usb_mount_point(self) -> Optional[str]:
        """Get USB mount point if available"""
        if self.usb_config_path:
            return os.path.dirname(self.usb_config_path)
        return None
