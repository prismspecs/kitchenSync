#!/usr/bin/env python3
"""
Refactored KitchenSync Auto-Start Script
Clean, modular implementation using the new architecture
"""

import os
import sys
import subprocess
import time
from pathlib import Path

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
    sys.path.insert(0, str(Path(__file__).parent / "src"))
    with open("/tmp/kitchensync_startup.log", "a") as f:
        f.write("✓ Added src to path\n")
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

    def run(self) -> bool:
        """Main execution flow"""
        print("\n🎬 KitchenSync Auto-Start")
        print("=" * 40)
        snapshot_env()

        # Step 1: Load configuration (defaults to collaborator if none found)
        if not self._load_configuration():
            ErrorDisplay.show_error("Failed to load configuration")
            return False

        # Decide role early
        is_leader = bool(getattr(self.config, "is_leader", False))

        if is_leader:
            # Leader flow: desktop background, video validation, update configs, start
            self._set_desktop_background()

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
        """Load configuration from USB drive; default to collaborator if none found"""
        print("🔍 Looking for USB drive configuration...")

        usb_config_path = USBConfigLoader.find_config_on_usb()
        if not usb_config_path:
            print("⚠️  No USB config found. Defaulting to COLLABORATOR mode.")
            # Create a default configuration (collaborator by default)
            self.config = ConfigManager()
            self.config.load_configuration()
            return True

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
            leader_updates = {**updates, "is_leader": "true", "pi_id": "leader-pi"}
            self.config.update_local_config("leader_config.ini", leader_updates)
        else:
            # Update collaborator config
            collaborator_updates = {
                **updates,
                "is_leader": "false",
                "pi_id": self.config.pi_id,
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
