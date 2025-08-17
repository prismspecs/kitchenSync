#!/usr/bin/env python3
"""
Refactored KitchenSync Auto-Start Script
Clean, modular implementation using the new architecture
"""

import os

import os
import sys
import subprocess
import time
from pathlib import Path
import zipfile
import shutil


# --- Upgrade logic will be called after config is loaded in main() ---
def apply_upgrade_if_available(usb_mount_point=None):
    # Prefer USB upgrade folder if available
    upgrade_dir = None
    if usb_mount_point:
        candidate = Path(usb_mount_point) / "upgrade"
        if candidate.exists():
            upgrade_dir = candidate
    if not upgrade_dir:
        candidate = Path(__file__).parent / "upgrade"
        if candidate.exists():
            upgrade_dir = candidate
    print("[UPGRADE] Checking for upgrade zip...")
    if not upgrade_dir:
        print("[UPGRADE] No upgrade directory found.")
        return
    zip_files = list(upgrade_dir.glob("*.zip"))
    if not zip_files:
        print("[UPGRADE] No upgrade zip found.")
        return
    zip_path = zip_files[0]
    log_path = "/tmp/kitchensync_startup.log"
    try:
        print(f"[UPGRADE] Found upgrade zip: {zip_path}")
        with open(log_path, "a") as f:
            f.write(f"\n[UPGRADE] Found upgrade zip: {zip_path}\n")
        # Extract to temp dir
        print(f"[UPGRADE] Extracting zip to temporary directory...")
        temp_dir = Path("/tmp/kitchensync_upgrade")
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
        temp_dir.mkdir(parents=True)
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(temp_dir)
        print(f"[UPGRADE] Replacing contents of {Path.home() / 'kitchenSync'}...")
        # Replace contents of ~/kitchenSync
        target_dir = Path.home() / "kitchenSync"
        # Remove everything in target_dir except upgrade folder and log
        for item in target_dir.iterdir():
            if item.name in ["upgrade", "kitchensync_startup.log"]:
                continue
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
        # Determine if extracted zip contains a single top-level folder
        extracted_items = list(temp_dir.iterdir())
        if len(extracted_items) == 1 and extracted_items[0].is_dir():
            # Copy contents of the folder
            for item in extracted_items[0].iterdir():
                dest = target_dir / item.name
                if item.is_dir():
                    shutil.copytree(item, dest)
                else:
                    shutil.copy2(item, dest)
        else:
            # Copy all items in temp_dir
            for item in extracted_items:
                dest = target_dir / item.name
                if item.is_dir():
                    shutil.copytree(item, dest)
                else:
                    shutil.copy2(item, dest)
        print(f"[UPGRADE] Upgrade applied from {zip_path}")
        with open(log_path, "a") as f:
            f.write(f"[UPGRADE] Upgrade applied from {zip_path}\n")
        # Delete zip and temp dir
        zip_path.unlink()
        shutil.rmtree(temp_dir)
        print(f"[UPGRADE] Upgrade zip deleted and temp cleaned up")
        with open(log_path, "a") as f:
            f.write(f"[UPGRADE] Upgrade zip deleted and temp cleaned up\n")
    except Exception as e:
        print(f"[UPGRADE] Upgrade failed: {e}", file=sys.stderr)
        with open(log_path, "a") as f:
            f.write(f"[UPGRADE] Upgrade failed: {e}\n")


# Emergency logging - capture startup issues
try:
    with open("/tmp/kitchensync_startup.log", "w") as f:
        f.write(f"KitchenSync startup at {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"PID: {os.getpid()}\n")
        f.write(f"User: {os.getenv('USER', 'unknown')}\n")
        f.write(f"Working dir: {os.getcwd()}\n")
        f.write(f"Python: {sys.executable}\n")
        f.write(f"Args: {sys.argv}\n")
        f.write("=" * 50 + "\n")
except Exception as e:
    # Last resort - write to stderr
    print(f"Emergency logging failed: {e}", file=sys.stderr)

# Add src to path
try:
    # Get the absolute path to the directory containing this script
    script_dir = Path(__file__).parent.resolve()
    src_path = script_dir / "src"
    sys.path.insert(0, str(src_path))

    with open("/tmp/kitchensync_startup.log", "a") as f:
        f.write(f"✓ Script dir: {script_dir}\n")
        f.write(f"✓ Added src to path: {src_path}\n")
except Exception as e:
    with open("/tmp/kitchensync_startup.log", "a") as f:
        f.write(f"✗ Failed to add src to path: {e}\n")
    print(f"Failed to add src to path: {e}", file=sys.stderr)

try:
    from config import ConfigManager, USBConfigLoader
    from video import VideoFileManager
    from ui import ErrorDisplay
    from core.logger import (
        log_info,
        log_warning,
        log_error,
        snapshot_env,
        log_file_paths,
    )

    with open("/tmp/kitchensync_startup.log", "a") as f:
        f.write("✓ All imports successful\n")

except Exception as e:
    with open("/tmp/kitchensync_startup.log", "a") as f:
        f.write(f"✗ Import failed: {e}\n")
    print(f"Import failed: {e}", file=sys.stderr)
    sys.exit(1)


class KitchenSyncAutoStart:
    """Simplified auto-start with clean configuration handling"""

    def __init__(self):
        self.config = None
        self.video_manager = None

    def _handle_no_config_found(self) -> bool:
        """Handle the case where no USB configuration is found."""
        print("⚠️  No USB config found. Defaulting to COLLABORATOR mode.")
        log_warning(
            "No USB config found, defaulting to collaborator", component="autostart"
        )

        # Create a default configuration for collaborator mode
        self.config = ConfigManager()
        self.config._create_default_config(
            is_leader=False
        )  # Explicitly set as collaborator

        # Update local configs for collaborator mode
        self._update_local_configs()

        # Start the collaborator role
        return self._start_role()

    def run(self) -> bool:
        """Main execution flow"""
        print("\n🎬 KitchenSync Auto-Start")
        print("=" * 40)
        snapshot_env()

        # Step 1: Load configuration
        if not self._load_configuration():
            # If loading fails because no config is found, handle it gracefully
            return self._handle_no_config_found()

        # Decide role early
        is_leader = bool(getattr(self.config, "is_leader", False))

        if is_leader:
            # Leader flow: desktop background, video validation, schedule check, update configs, start
            self._set_desktop_background()
            self._check_usb_schedule()

            if not self._validate_video():
                ErrorDisplay.show_error("No valid video file found")
                return False

            self._update_local_configs()
            return self._start_role()
        else:
            # Collaborator flow: skip video validation (collaborator handles no-video)
            self._update_local_configs()
            return self._start_role()

    def _load_configuration(self) -> bool:
        """Load configuration from USB drive."""
        print("🔍 Looking for USB drive configuration...")

        usb_config_path = USBConfigLoader.find_config_on_usb()
        if not usb_config_path:
            return False  # Signal that no config was found

        self.config = ConfigManager()
        self.config.usb_config_path = usb_config_path
        self.config.load_configuration()

        print(f"✓ Found config: {usb_config_path}")
        return True

    def _validate_video(self) -> bool:
        """Validate video file availability"""
        self.video_manager = VideoFileManager(
            self.config.video_file, self.config.usb_mount_point
        )

        video_path = self.video_manager.find_video_file()
        if video_path:
            print(f"✅ Video file: {video_path}")
            log_info(f"Video candidate: {video_path}", component="autostart")
            return True

        return False

    def _set_desktop_background(self) -> None:
        """Set desktop background if available"""
        if not self.config.usb_mount_point:
            return

        background_path = os.path.join(
            self.config.usb_mount_point, "desktop-background.png"
        )
        if os.path.exists(background_path):
            try:
                # Try different desktop environment commands
                commands = [
                    [
                        "gsettings",
                        "set",
                        "org.gnome.desktop.background",
                        "picture-uri",
                        f"file://{background_path}",
                    ],
                    ["pcmanfm", "--set-wallpaper", background_path],
                    ["feh", "--bg-scale", background_path],
                ]

                for cmd in commands:
                    try:
                        subprocess.run(cmd, check=True, capture_output=True)
                        print(f"✅ Set desktop background: {background_path}")
                        break
                    except (subprocess.CalledProcessError, FileNotFoundError):
                        continue

            except Exception as e:
                print(f"⚠️ Could not set desktop background: {e}")

    def _check_usb_schedule(self) -> None:
        """Check for and report USB schedule files"""
        if not self.config.usb_mount_point:
            return

        try:
            usb_schedule_path = USBConfigLoader.find_schedule_on_usb()
            if usb_schedule_path:
                print(f"🎵 Found MIDI schedule: {usb_schedule_path}")
                log_info(
                    f"USB MIDI schedule: {usb_schedule_path}", component="autostart"
                )
            else:
                print(
                    "📋 No MIDI schedule found on USB - will use local/empty schedule"
                )

            # Also check for MIDI files that could be converted
            usb_midi_path = USBConfigLoader.find_midi_file_on_usb()
            if usb_midi_path:
                print(f"🎼 Found MIDI file: {usb_midi_path} (not auto-converted)")
                log_info(f"USB MIDI file: {usb_midi_path}", component="autostart")

        except Exception as e:
            print(f"⚠️ Error checking USB schedule: {e}")

    def _update_local_configs(self) -> None:
        """Update local configuration files"""
        # Common updates for both roles
        updates = {
            "video_file": self.config.video_file,
            "debug": str(self.config.debug_mode).lower(),
            "usb_mount_point": self.config.usb_mount_point or "",
        }

        if self.config.is_leader:
            # Update leader config
            leader_updates = {**updates, "is_leader": "true", "device_id": "leader-pi"}
            self.config.update_local_config("leader_config.ini", leader_updates)
        else:
            # Update collaborator config
            collaborator_updates = {
                **updates,
                "is_leader": "false",
                "device_id": self.config.device_id,
                "midi_port": self.config.get("midi_port", "0"),
            }

            # Try different collaborator config files
            for config_file in [
                "collaborator_config.ini",
                "collaborator_config_pi2.ini",
                "collaborator_config_pi3.ini",
            ]:
                if os.path.exists(config_file):
                    self.config.update_local_config(config_file, collaborator_updates)
                    break
            else:
                # Create default collaborator config
                self.config.update_local_config(
                    "collaborator_config.ini", collaborator_updates
                )

    def _start_role(self) -> bool:
        """Start leader or collaborator based on configuration"""
        debug_flag = ["--debug"] if self.config.debug_mode else []

        try:
            if self.config.is_leader:
                print("🎯 Starting as LEADER...")
                cmd = (
                    [sys.executable, "leader.py", "--auto"] + debug_flag + sys.argv[1:]
                )
            else:
                print("🎵 Starting as COLLABORATOR...")
                cmd = [sys.executable, "collaborator.py"] + debug_flag + sys.argv[1:]

            print(f"🚀 Executing: {' '.join(cmd)}")
            log_info(f"Exec: {' '.join(cmd)}", component="autostart")
            os.execv(sys.executable, cmd)

        except Exception as e:
            ErrorDisplay.show_error("Failed to start role", str(e))
            return False

    def _show_manual_instructions(self) -> None:
        """Show manual operation instructions"""
        print("\n💡 No USB configuration found. Manual operation available:")
        print("Available commands:")
        print("  python3 leader.py     - Start as leader")
        print("  python3 collaborator.py - Start as collaborator")
        print("")
        print("Or use the legacy scripts:")
        print("  python3 leader.py         - Original leader script")
        print("  python3 collaborator.py   - Original collaborator script")


def main():
    """Main entry point"""
    try:
        auto_start = KitchenSyncAutoStart()
        # Load config first to get USB mount point
        loaded = auto_start._load_configuration()
        usb_mount = None
        if loaded and hasattr(auto_start.config, "usb_mount_point"):
            usb_mount = auto_start.config.usb_mount_point
        # Run upgrade check with correct mount point
        apply_upgrade_if_available(usb_mount)
        # Continue with normal run
        success = auto_start.run()
        if not success:
            sys.exit(1)
    except KeyboardInterrupt:
        print("\n👋 Interrupted by user")
        sys.exit(0)
    except Exception as e:
        ErrorDisplay.show_error("Fatal error", str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
