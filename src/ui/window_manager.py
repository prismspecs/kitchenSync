#!/usr/bin/env python3
"""
Cross-platform window management for KitchenSync
Supports both X11 (wmctrl) and Wayland (wlrctl)
"""

import os
import subprocess
import time
from typing import Optional, List, Tuple
from src.core.logger import log_info, log_warning, log_error


class WindowManager:
    """Cross-platform window manager that works with both X11 and Wayland"""

    def __init__(self):
        self.is_wayland = self._detect_wayland()
        self.window_tool = "wlrctl" if self.is_wayland else "wmctrl"
        log_info(f"Window manager initialized for {'Wayland' if self.is_wayland else 'X11'} using {self.window_tool}")

    def _detect_wayland(self) -> bool:
        """Detect if we're running under Wayland"""
        # Check environment variables
        if os.environ.get("WAYLAND_DISPLAY"):
            return True
        if os.environ.get("XDG_SESSION_TYPE") == "wayland":
            return True
        
        # Check if wlrctl is available and working
        try:
            result = subprocess.run(
                ["wlrctl", "toplevel", "list"], 
                capture_output=True, 
                timeout=2
            )
            if result.returncode == 0:
                return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        
        return False

    def list_windows(self) -> List[str]:
        """List all windows"""
        try:
            if self.is_wayland:
                result = subprocess.run(
                    ["wlrctl", "toplevel", "list"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
            else:
                result = subprocess.run(
                    ["wmctrl", "-l"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
            
            if result.returncode == 0:
                return result.stdout.strip().split("\n")
            else:
                log_warning(f"Failed to list windows: {result.stderr}")
                return []
                
        except Exception as e:
            log_error(f"Exception listing windows: {e}")
            return []

    def find_window(self, search_terms: List[str], exclude_terms: List[str] = None) -> Optional[str]:
        """Find a window by searching for terms in the window list"""
        if exclude_terms is None:
            exclude_terms = []
            
        windows = self.list_windows()
        
        for line in windows:
            if not line.strip():
                continue
                
            line_lower = line.lower()
            
            # Check if any search term matches
            term_found = any(term.lower() in line_lower for term in search_terms)
            
            # Check if any exclude term matches
            exclude_found = any(term.lower() in line_lower for term in exclude_terms)
            
            if term_found and not exclude_found:
                if self.is_wayland:
                    # wlrctl format: app_id window_title
                    return line.strip()
                else:
                    # wmctrl format: window_id desktop class hostname window_title
                    parts = line.split(None, 4)
                    if len(parts) >= 1:
                        return parts[0]  # Return window ID
        
        # If no exact match, try partial matches for window titles
        for line in windows:
            if not line.strip():
                continue
                
            line_lower = line.lower()
            
            # Check for partial matches in window titles (more flexible)
            for term in search_terms:
                term_lower = term.lower()
                if term_lower in line_lower:
                    # Check if any exclude term matches
                    exclude_found = any(exclude.lower() in line_lower for exclude in exclude_terms)
                    if not exclude_found:
                        if self.is_wayland:
                            return line.strip()
                        else:
                            parts = line.split(None, 4)
                            if len(parts) >= 1:
                                return parts[0]
        
        return None

    def _detect_coordinate_offset(self, window_identifier: str, target_x: int, target_y: int) -> Tuple[int, int]:
        """Detect and return coordinate offset for a window"""
        try:
            result = subprocess.run(
                ["wmctrl", "-lG"], capture_output=True, text=True, timeout=5
            )
            
            if result.returncode == 0:
                for line in result.stdout.strip().split("\n"):
                    if window_identifier in line:
                        parts = line.split()
                        if len(parts) >= 5:
                            actual_x = int(parts[2])
                            actual_y = int(parts[3])
                            
                            offset_x = actual_x - target_x
                            offset_y = actual_y - target_y
                            
                            log_info(f"Coordinate offset detected: ({offset_x}, {offset_y})")
                            return offset_x, offset_y
                            
        except Exception as e:
            log_warning(f"Failed to detect coordinate offset: {e}")
            
        return 0, 0

    def get_display_geometry(self) -> Tuple[int, int]:
        """Get the current display geometry (width, height)"""
        try:
            if self.is_wayland:
                # For Wayland, try to get from environment or use defaults
                width = int(os.environ.get("WLR_HEADLESS_WIDTH", "1920"))
                height = int(os.environ.get("WLR_HEADLESS_HEIGHT", "1080"))
                return width, height
            else:
                # For X11, try to get from xrandr or use defaults
                try:
                    result = subprocess.run(
                        ["xrandr", "--current"], 
                        capture_output=True, 
                        text=True, 
                        timeout=5
                    )
                    if result.returncode == 0:
                        for line in result.stdout.split("\n"):
                            if "*" in line:  # Current mode
                                parts = line.split()
                                if len(parts) >= 2:
                                    resolution = parts[1]
                                    if "x" in resolution:
                                        w, h = resolution.split("x")
                                        return int(w), int(h)
                except:
                    pass
                
                # Fallback to environment variables or defaults
                width = int(os.environ.get("DISPLAY_WIDTH", "1920"))
                height = int(os.environ.get("DISPLAY_HEIGHT", "1080"))
                return width, height
                
        except Exception as e:
            log_warning(f"Failed to get display geometry: {e}")
            return 1920, 1080  # Default fallback

    def position_window(self, window_identifier: str, x: int, y: int, width: int, height: int) -> bool:
        """Position a window at the specified coordinates"""
        try:
            if self.is_wayland:
                # Note: wlrctl may have limited positioning support
                # Try to focus first
                subprocess.run(
                    ["wlrctl", "toplevel", "focus", window_identifier],
                    check=False,
                    timeout=5
                )
                log_info(f"Focused Wayland window: {window_identifier}")
                return True
            else:
                # X11 with wmctrl - try multiple approaches
                # First, try to move the window
                move_result = subprocess.run(
                    ["wmctrl", "-ir", window_identifier, "-e", f"0,{x},{y},{width},{height}"],
                    check=False,
                    timeout=5,
                    capture_output=True,
                    text=True
                )
                
                if move_result.returncode == 0:
                    log_info(f"Positioned X11 window {window_identifier} to ({x},{y},{width},{height})")
                    
                    # Verify the positioning worked by checking window position
                    time.sleep(0.2)  # Give it time to move
                    verify_result = subprocess.run(
                        ["wmctrl", "-lG"], capture_output=True, text=True, timeout=5
                    )
                    
                    if verify_result.returncode == 0:
                        for line in verify_result.stdout.strip().split("\n"):
                            if window_identifier in line:
                                log_info(f"Window position verified: {line.strip()}")
                                
                                # Parse the actual position to check for coordinate offset
                                try:
                                    parts = line.split()
                                    if len(parts) >= 5:
                                        actual_x = int(parts[2])
                                        actual_y = int(parts[3])
                                        actual_w = int(parts[4])
                                        actual_h = int(parts[5])
                                        
                                        log_info(f"Actual position: ({actual_x}, {actual_y}) {actual_w}x{actual_h}")
                                        
                                        # If there's a significant offset, log it for debugging
                                        if abs(actual_x - x) > 100 or abs(actual_y - y) > 100:
                                            log_warning(f"Large coordinate offset detected: requested ({x},{y}), got ({actual_x},{actual_y})")
                                except (ValueError, IndexError) as e:
                                    log_warning(f"Could not parse window position: {e}")
                                break
                    
                    return True
                else:
                    log_warning(f"Failed to position X11 window: {move_result.stderr}")
                    
                    # Try alternative approach - move and resize separately
                    log_info("Trying alternative positioning approach...")
                    
                    # First move the window
                    move_only = subprocess.run(
                        ["wmctrl", "-ir", window_identifier, "-e", f"0,{x},{y},-1,-1"],
                        check=False,
                        timeout=5,
                        capture_output=True,
                        text=True
                    )
                    
                    if move_only.returncode == 0:
                        log_info(f"Moved window to ({x},{y})")
                        
                        # Then resize it
                        resize_only = subprocess.run(
                            ["wmctrl", "-ir", window_identifier, "-e", f"0,-1,-1,{width},{height}"],
                            check=False,
                            timeout=5,
                            capture_output=True,
                            text=True
                        )
                        
                        if resize_only.returncode == 0:
                            log_info(f"Resized window to {width}x{height}")
                            return True
                        else:
                            log_warning(f"Resize failed: {resize_only.stderr}")
                    else:
                        log_warning(f"Move failed: {move_only.stderr}")
                    
                    return False
                    
        except Exception as e:
            log_error(f"Exception positioning window: {e}")
            return False

    def focus_window(self, window_identifier: str) -> bool:
        """Focus a window"""
        try:
            if self.is_wayland:
                result = subprocess.run(
                    ["wlrctl", "toplevel", "focus", window_identifier],
                    check=False,
                    timeout=5,
                    capture_output=True,
                    text=True
                )
            else:
                result = subprocess.run(
                    ["wmctrl", "-ia", window_identifier],
                    check=False,
                    timeout=5,
                    capture_output=True,
                    text=True
                )
            
            if result.returncode == 0:
                log_info(f"Focused window: {window_identifier}")
                return True
            else:
                log_warning(f"Failed to focus window: {result.stderr}")
                return False
                
        except Exception as e:
            log_error(f"Exception focusing window: {e}")
            return False

    def wait_for_window(self, search_terms: List[str], exclude_terms: List[str] = None, timeout: int = 10) -> Optional[str]:
        """Wait for a window to appear"""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            window = self.find_window(search_terms, exclude_terms)
            if window:
                return window
            time.sleep(0.2)  # Reduced from 0.5s to 0.2s for faster detection
        
        log_warning(f"Window with terms {search_terms} not found within {timeout} seconds")
        return None

    def get_window_details(self) -> str:
        """Get detailed window information for debugging"""
        try:
            if self.is_wayland:
                result = subprocess.run(
                    ["wlrctl", "toplevel", "list"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
            else:
                result = subprocess.run(
                    ["wmctrl", "-lG"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
            
            if result.returncode == 0:
                return result.stdout
            else:
                return f"Failed to get window details: {result.stderr}"
                
        except Exception as e:
            return f"Exception getting window details: {e}"

    def debug_window_search(self, search_terms: List[str], exclude_terms: List[str] = None) -> str:
        """Debug method to show what windows are found and why matches fail"""
        if exclude_terms is None:
            exclude_terms = []
            
        windows = self.list_windows()
        debug_info = f"Searching for windows with terms: {search_terms}\n"
        debug_info += f"Excluding terms: {exclude_terms}\n"
        debug_info += f"Display type: {'Wayland' if self.is_wayland else 'X11'}\n"
        debug_info += f"Window tool: {self.window_tool}\n"
        debug_info += f"Total windows found: {len(windows)}\n\n"
        
        for i, line in enumerate(windows):
            if not line.strip():
                continue
                
            line_lower = line.lower()
            debug_info += f"Window {i}: {line}\n"
            
            # Check search terms
            search_matches = []
            for term in search_terms:
                if term.lower() in line_lower:
                    search_matches.append(term)
            
            # Check exclude terms
            exclude_matches = []
            for term in exclude_terms:
                if term.lower() in line_lower:
                    exclude_matches.append(term)
            
            debug_info += f"  Search matches: {search_matches}\n"
            debug_info += f"  Exclude matches: {exclude_matches}\n"
            debug_info += f"  Would match: {bool(search_matches and not exclude_matches)}\n\n"
        
        return debug_info

