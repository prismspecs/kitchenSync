#!/usr/bin/env python3
"""
KitchenSync Auto-Start Script
Automatically detects USB drive configuration and starts as leader or collaborator
"""

import os
import sys
import subprocess
import configparser
import glob
import time

class KitchenSyncAutoStart:
    def __init__(self):
        self.usb_config = None
        self.usb_mount_point = None
        self.video_file = None
        
    def find_usb_config(self):
        """Find and load kitchensync.ini from USB drive"""
        print("🔍 Looking for USB drive configuration...")
        
        # Check for mounted USB drives
        try:
            mount_result = subprocess.run(['mount'], capture_output=True, text=True)
            if mount_result.returncode == 0:
                for line in mount_result.stdout.split('\n'):
                    if '/media/' in line and ('usb' in line.lower() or 'sd' in line or 'mmc' in line):
                        parts = line.split(' on ')
                        if len(parts) >= 2:
                            mount_point = parts[1].split(' type ')[0]
                            if os.path.exists(mount_point) and os.path.isdir(mount_point):
                                config_path = os.path.join(mount_point, 'kitchensync.ini')
                                if os.path.exists(config_path):
                                    print(f"✓ Found config file: {config_path}")
                                    self.usb_mount_point = mount_point
                                    return self.load_config(config_path)
                                else:
                                    print(f"⚠️  USB drive found at {mount_point} but no kitchensync.ini file")
        except Exception as e:
            print(f"Error checking USB drives: {e}")
        
        print("❌ No USB configuration found")
        return False
    
    def load_config(self, config_path):
        """Load configuration from USB drive"""
        try:
            self.usb_config = configparser.ConfigParser()
            self.usb_config.read(config_path)
            
            if 'KITCHENSYNC' not in self.usb_config:
                print("❌ Invalid config file: missing [KITCHENSYNC] section")
                return False
            
            config = self.usb_config['KITCHENSYNC']
            print(f"✓ Pi ID: {config.get('pi_id', 'UNKNOWN')}")
            print(f"✓ Role: {'Leader' if config.getboolean('is_leader', False) else 'Collaborator'}")
            
            return True
            
        except Exception as e:
            print(f"❌ Error loading config: {e}")
            return False
    
    def find_video_files(self):
        """Find video files on USB drive"""
        if not self.usb_mount_point:
            return []
        
        video_extensions = ['.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv', '.webm', '.m4v']
        video_files = []
        
        try:
            for file in os.listdir(self.usb_mount_point):
                file_path = os.path.join(self.usb_mount_point, file)
                if os.path.isfile(file_path):
                    _, ext = os.path.splitext(file.lower())
                    if ext in video_extensions:
                        video_files.append(file)
            
            return video_files
            
        except Exception as e:
            print(f"Error scanning for videos: {e}")
            return []
    
    def select_video_file(self):
        """Select appropriate video file based on config and availability"""
        video_files = self.find_video_files()
        config = self.usb_config['KITCHENSYNC']
        
        print(f"📹 Found {len(video_files)} video file(s): {video_files}")
        
        # Check if specific video file is configured
        specified_video = config.get('video_file', '').strip()
        
        if specified_video:
            if specified_video in video_files:
                self.video_file = os.path.join(self.usb_mount_point, specified_video)
                print(f"✓ Using specified video: {specified_video}")
                return True
            else:
                print(f"⚠️  Specified video '{specified_video}' not found, checking available videos...")
        
        # Handle video file selection
        if len(video_files) == 0:
            self.show_error("No video files found on USB drive")
            return False
        elif len(video_files) == 1:
            self.video_file = os.path.join(self.usb_mount_point, video_files[0])
            print(f"✓ Using single video file: {video_files[0]}")
            return True
        else:
            # Multiple videos and no specific file configured
            if not specified_video:
                self.show_error(f"Multiple video files found ({len(video_files)}) but no specific file configured in kitchensync.ini")
                return False
            else:
                self.show_error(f"Specified video '{specified_video}' not found. Available: {', '.join(video_files)}")
                return False
    
    def show_error(self, message):
        """Display error message on HDMI output"""
        print(f"❌ ERROR: {message}")
        
        # Try to display error with various methods
        try:
            # Method 1: Try to use notify-send (if available and DISPLAY is set)
            if os.environ.get('DISPLAY'):
                subprocess.run(['notify-send', 'KitchenSync Error', message], 
                             capture_output=True, timeout=5)
        except:
            pass
        
        try:
            # Method 2: Try to create a simple GUI error dialog (if DISPLAY available)
            if os.environ.get('DISPLAY'):
                error_script = f'''
import tkinter as tk
from tkinter import messagebox
import sys

try:
    root = tk.Tk()
    root.withdraw()
    messagebox.showerror("KitchenSync Error", "{message}")
    root.quit()
except:
    pass
'''
                subprocess.run([sys.executable, '-c', error_script], 
                             capture_output=True, timeout=10)
        except:
            pass
        
        # Method 3: Always log to syslog and console
        try:
            subprocess.run(['logger', '-t', 'kitchensync', f'ERROR: {message}'], 
                         capture_output=True, timeout=5)
        except:
            pass
            
        print("\n" + "="*60)
        print("KITCHENSYNC ERROR")
        print("="*60)
        print(f"{message}")
        print("="*60)
        print("Please check your USB drive configuration and try again.")
        print("="*60 + "\n")
    
    def update_local_config(self):
        """Update local config files with USB settings"""
        config = self.usb_config['KITCHENSYNC']
        
        # Update collaborator config
        if os.path.exists('collaborator_config.ini'):
            local_config = configparser.ConfigParser()
            local_config.read('collaborator_config.ini')
            
            if 'DEFAULT' not in local_config:
                local_config['DEFAULT'] = {}
            
            local_config['DEFAULT']['pi_id'] = config.get('pi_id', 'pi-unknown')
            local_config['DEFAULT']['video_file'] = os.path.basename(self.video_file) if self.video_file else ''
            local_config['DEFAULT']['midi_port'] = config.get('midi_port', '0')
            
            with open('collaborator_config.ini', 'w') as f:
                local_config.write(f)
            
            print("✓ Updated local collaborator configuration")
    
    def start_appropriate_role(self):
        """Start leader or collaborator based on configuration"""
        config = self.usb_config['KITCHENSYNC']
        is_leader = config.getboolean('is_leader', False)
        
        if is_leader:
            print("🎯 Starting as LEADER...")
            # Start leader in automatic mode
            os.execv(sys.executable, [sys.executable, 'leader.py', '--auto'] + sys.argv[1:])
        else:
            print("🎵 Starting as COLLABORATOR...")
            self.update_local_config()
            os.execv(sys.executable, [sys.executable, 'collaborator.py'] + sys.argv[1:])
    
    def run(self):
        """Main execution flow"""
        print("\n🎬 KitchenSync Auto-Start")
        print("=" * 40)
        
        # Step 1: Find USB configuration
        if not self.find_usb_config():
            print("\n💡 No USB configuration found. Starting in manual mode...")
            print("Available commands:")
            print("  python3 leader.py     - Start as leader")
            print("  python3 collaborator.py - Start as collaborator")
            return False
        
        # Step 2: Select video file
        if not self.select_video_file():
            return False
        
        # Step 3: Start appropriate role
        try:
            self.start_appropriate_role()
        except KeyboardInterrupt:
            print("\n👋 Interrupted by user")
            return False
        except Exception as e:
            print(f"❌ Error starting: {e}")
            return False

if __name__ == "__main__":
    auto_start = KitchenSyncAutoStart()
    success = auto_start.run()
    sys.exit(0 if success else 1)
