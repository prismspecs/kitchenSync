#!/usr/bin/env python3
"""
kSync Universal Node Bootstrapper
Handles role detection (Leader, Collaborator, Bystander) and process execution.
Prioritizes ksync.ini on USB root.
"""

import os
import sys
import subprocess
from pathlib import Path
import zipfile
import shutil

# Add src to path
script_dir = Path(__file__).parent.resolve()
sys.path.insert(0, str(script_dir / "src"))

try:
    from config import ConfigManager, USBConfigLoader
    from video import VideoFileManager
    from ui import ErrorDisplay
    from networking.wifi_manager import ensure_network
    from core.logger import (
        log_info,
        log_warning,
        log_error,
        snapshot_env,
    )
except ImportError as e:
    print(f"Boot Error: Failed to import core modules: {e}", file=sys.stderr)
    sys.exit(1)


def apply_upgrade_if_available(usb_mount_point=None):
    """Check for and apply software upgrades from USB or local folder."""
    upgrade_dir = None
    if usb_mount_point:
        candidate = Path(usb_mount_point) / "upgrade"
        if candidate.exists():
            upgrade_dir = candidate
    
    if not upgrade_dir:
        candidate = script_dir / "upgrade"
        if candidate.exists():
            upgrade_dir = candidate

    if not upgrade_dir:
        return

    zip_files = list(upgrade_dir.glob("*.zip"))
    if not zip_files:
        return

    zip_path = zip_files[0]
    print(f"[UPGRADE] Found upgrade zip: {zip_path}")
    
    try:
        temp_dir = Path("/tmp/kitchensync_upgrade")
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
        temp_dir.mkdir(parents=True)
        
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(temp_dir)
            
        target_dir = script_dir
        # Simple/clean replacement logic
        for item in target_dir.iterdir():
            if item.name in ["upgrade", ".git", ".gitignore", "media", "logs"]:
                continue
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
                
        extracted_items = list(temp_dir.iterdir())
        if len(extracted_items) == 1 and extracted_items[0].is_dir():
            for item in extracted_items[0].iterdir():
                dest = target_dir / item.name
                if item.is_dir():
                    shutil.copytree(item, dest)
                else:
                    shutil.copy2(item, dest)
        else:
            for item in extracted_items:
                dest = target_dir / item.name
                if item.is_dir():
                    shutil.copytree(item, dest)
                else:
                    shutil.copy2(item, dest)
                    
        print(f"[UPGRADE] Upgrade applied. Deleting zip.")
        zip_path.unlink()
        shutil.rmtree(temp_dir)
    except Exception as e:
        print(f"[UPGRADE] Failed: {e}", file=sys.stderr)


class kSyncAutoStart:
    """Universal Node Manager"""

    def __init__(self):
        self.config = None
        self.video_manager = None

    def run(self) -> bool:
        """Main execution flow"""
        print("\nkSync Universal Node")
        print("=" * 40)
        snapshot_env()

        # 1. Load configuration (prioritizes USB ksync.ini root)
        if not self._load_configuration():
            return self._handle_no_config_found()

        role = self.config.role_name()
        print(f" Role: {role.upper()}")

        # 2. Update local persistence
        self._update_local_configs()

        # 3. Network bootstrap (ethernet > saved/venue WiFi > kSync private
        # network; see docs/WIFI_PROVISIONING.md). Never blocks boot on
        # failure — collaborators keep joining in the background via NM.
        network_state = ensure_network(self.config)
        log_info(f"Network bootstrap result: {network_state}", component="autostart")

        # 4. Role-specific setup
        if role == "leader":
            self._set_desktop_background()
            self._check_usb_schedule()
            if not self._validate_video():
                print(" Warning: Leader has no valid video file.")
        
        return self._start_role()

    def _load_configuration(self) -> bool:
        """Load ksync.ini, prioritizing USB root."""
        # Check USB (prioritizes root)
        usb_config_path = USBConfigLoader.find_config_on_usb()
        if usb_config_path:
            self.config = ConfigManager(usb_config_path)
            print(f" Loaded configuration from USB: {usb_config_path}")
            return True
            
        # Check local
        if os.path.exists("ksync.ini"):
            self.config = ConfigManager("ksync.ini")
            print(" Loaded configuration from local ksync.ini")
            return True

        return False

    def _handle_no_config_found(self) -> bool:
        """Enter Bystander mode if no config is present."""
        print(" No configuration found. Entering BYSTANDER mode.")
        log_warning("No ksync.ini found, entering bystander mode", component="autostart")

        self.config = ConfigManager()
        self.config._create_default_config(role="bystander")
        self._update_local_configs()
        return self._start_role()

    def _validate_video(self) -> bool:
        """Validate video file availability"""
        self.video_manager = VideoFileManager(
            self.config.video_file, self.config.usb_mount_point
        )
        video_path = self.video_manager.find_video_file()
        if video_path:
            print(f" Video file: {video_path}")
            return True
        return False

    def _set_desktop_background(self) -> None:
        """Set desktop background if available"""
        background_path = None
        if self.config.usb_mount_point:
            usb_bg = os.path.join(self.config.usb_mount_point, "desktop-background.png")
            if os.path.exists(usb_bg):
                background_path = usb_bg

        if not background_path:
            local_bg = script_dir / "src" / "ui" / "assets" / "desktop-background.png"
            if local_bg.exists():
                background_path = str(local_bg)

        if background_path:
            commands = [
                ["pcmanfm", "--set-wallpaper", background_path],
                ["feh", "--bg-scale", background_path],
            ]
            for cmd in commands:
                try:
                    subprocess.run(cmd, check=True, capture_output=True)
                    break
                except Exception:
                    continue

    def _check_usb_schedule(self) -> None:
        if not self.config.usb_mount_point: return
        usb_schedule_path = USBConfigLoader.find_schedule_on_usb()
        if usb_schedule_path:
            log_info(f"USB MIDI schedule: {usb_schedule_path}", component="autostart")

    def _update_local_configs(self) -> None:
        """Persist current configuration to local ksync.ini"""
        updates = {
            "role": self.config.role_name(),
            "device_id": self.config.device_id,
            "video_file": self.config.video_file,
            "overlay": str(self.config.debug_mode).lower(),
            "usb_mount_point": self.config.usb_mount_point or "",
        }
        self.config.update_local_config("ksync.ini", updates)

    def _start_role(self) -> bool:
        """Switch process to assigned role"""
        debug_flag = ["--debug"] if self.config.debug_mode else []
        role = self.config.role_name()
        
        try:
            if role == "leader":
                cmd = [sys.executable, "leader.py", "--auto", "--config", "ksync.ini"] + debug_flag
            else:
                # Collaborator and Bystander logic consolidated in collaborator.py
                cmd = [sys.executable, "collaborator.py", "--config", "ksync.ini"] + debug_flag

            log_info(f"Execv: {' '.join(cmd)}", component="autostart")
            os.execv(sys.executable, cmd)
        except Exception as e:
            ErrorDisplay.show_error("Failed to launch role", str(e))
            return False


def main():
    try:
        auto_start = kSyncAutoStart()
        # Upgrade check
        usb_config = USBConfigLoader.find_config_on_usb()
        usb_mount = os.path.dirname(usb_config) if usb_config else None
        apply_upgrade_if_available(usb_mount)
        
        if not auto_start.run():
            sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(0)
    except Exception as e:
        print(f"Fatal error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
