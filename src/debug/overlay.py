#!/usr/bin/env python3
"""
Debug Overlay System for KitchenSync
Provides visual and text-based debug information display
"""

import os
import subprocess
import tempfile
import threading
import time
from typing import List, Optional, Dict, Any

# Try to import pygame for visual overlay
try:
    import pygame
    PYGAME_AVAILABLE = True
except ImportError:
    PYGAME_AVAILABLE = False


class DebugError(Exception):
    """Raised when debug overlay operations fail"""
    pass


class DebugOverlay:
    """Debug overlay system with pygame and text fallback modes"""
    
    def __init__(self, pi_id: str, video_file: str, use_pygame: bool = True):
        self.pi_id = pi_id
        self.video_file = video_file
        self.use_pygame = use_pygame and PYGAME_AVAILABLE
        
        # Display settings
        self.overlay_width = 400
        self.overlay_height = 200
        self.overlay_x = 1520  # Position to right of video
        self.overlay_y = 0
        
        # State
        self.screen = None
        self.font = None
        self.clock = None
        self.keep_on_top = False
        self.raise_thread = None
        
        # Initialize overlay
        if self.use_pygame:
            self._init_pygame_overlay()
        else:
            print(f"🐛 Text-based debug overlay initialized for {pi_id}")
    
    def _init_pygame_overlay(self) -> None:
        """Initialize pygame overlay for visual debug display"""
        try:
            os.environ['SDL_VIDEO_WINDOW_POS'] = f'{self.overlay_x},{self.overlay_y}'
            
            pygame.init()
            pygame.display.set_caption("KitchenSync Debug")
            
            self.screen = pygame.display.set_mode((self.overlay_width, self.overlay_height))
            self.font = pygame.font.Font(None, 24)
            self.clock = pygame.time.Clock()
            
            # Set window to stay on top
            self.keep_on_top = True
            self.raise_thread = threading.Thread(target=self._window_raise_loop, daemon=True)
            self.raise_thread.start()
            
            print(f"✓ Pygame debug overlay initialized for {self.pi_id}")
            
        except Exception as e:
            print(f"⚠️ Pygame overlay init failed: {e}, falling back to text mode")
            self.use_pygame = False
    
    def _window_raise_loop(self) -> None:
        """Keep debug window on top"""
        while self.keep_on_top:
            try:
                # Use wmctrl to keep window on top
                subprocess.run(['wmctrl', '-r', 'KitchenSync Debug', '-b', 'add,above'], 
                              capture_output=True, timeout=1)
            except Exception:
                pass
            time.sleep(2)  # Check every 2 seconds
    
    def update_display(self, current_time: float = 0, total_time: float = 0, 
                      additional_info: Optional[List[str]] = None) -> None:
        """Update the debug overlay display"""
        if self.use_pygame:
            self._update_pygame_display(current_time, total_time, additional_info)
        else:
            self._update_text_display(current_time, total_time, additional_info)
    
    def _update_pygame_display(self, current_time: float, total_time: float, 
                              additional_info: Optional[List[str]]) -> None:
        """Update pygame-based visual overlay"""
        try:
            # Handle pygame events
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return
            
            # Clear screen
            self.screen.fill((0, 0, 0))  # Black background
            
            # Format time display
            current_min = int(current_time // 60)
            current_sec = int(current_time % 60)
            total_min = int(total_time // 60)
            total_sec = int(total_time % 60)
            time_str = f"{current_min:02d}:{current_sec:02d}/{total_min:02d}:{total_sec:02d}"
            
            # Basic info
            y_offset = 10
            line_height = 25
            
            # Pi ID and video
            text = self.font.render(f"Pi: {self.pi_id}", True, (255, 255, 255))
            self.screen.blit(text, (10, y_offset))
            y_offset += line_height
            
            # Time
            text = self.font.render(f"Time: {time_str}", True, (0, 255, 0))
            self.screen.blit(text, (10, y_offset))
            y_offset += line_height
            
            # Video file
            video_name = os.path.basename(self.video_file)
            if len(video_name) > 20:
                video_name = video_name[:17] + "..."
            text = self.font.render(f"Video: {video_name}", True, (200, 200, 200))
            self.screen.blit(text, (10, y_offset))
            y_offset += line_height
            
            # Additional info
            if additional_info:
                for info in additional_info[:4]:  # Limit to 4 lines
                    if len(info) > 30:
                        info = info[:27] + "..."
                    text = self.font.render(info, True, (255, 255, 0))
                    self.screen.blit(text, (10, y_offset))
                    y_offset += line_height
            
            pygame.display.flip()
            self.clock.tick(10)  # 10 FPS to avoid overwhelming system
            
        except Exception as e:
            print(f"Error updating pygame overlay: {e}")
    
    def _update_text_display(self, current_time: float, total_time: float, 
                            additional_info: Optional[List[str]]) -> None:
        """Update text-based debug display (fallback)"""
        # Format time
        current_min = int(current_time // 60)
        current_sec = int(current_time % 60)
        total_min = int(total_time // 60)
        total_sec = int(total_time % 60)
        time_str = f"{current_min:02d}:{current_sec:02d}/{total_min:02d}:{total_sec:02d}"
        
        # Print debug info to console (every 5 seconds to avoid spam)
        if int(current_time) % 5 == 0 and current_time > 0:
            print(f"🐛 DEBUG | Pi: {self.pi_id} | Video: {self.video_file} | Time: {time_str}")
            if additional_info:
                for info in additional_info[:2]:
                    print(f"🐛        | {info}")
    
    def cleanup(self) -> None:
        """Clean up overlay resources"""
        if self.use_pygame:
            try:
                # Stop the window raising thread
                self.keep_on_top = False
                if self.raise_thread:
                    self.raise_thread.join(timeout=1)
                
                pygame.quit()
                print("✓ Pygame debug overlay cleaned up")
            except Exception as e:
                print(f"Error cleaning up pygame overlay: {e}")


class TerminalDebugger:
    """Terminal-based debug display for leader"""
    
    def __init__(self):
        self.terminal_process = None
        self.pipe_path = "/tmp/kitchensync_debug"
        self._start_debug_terminal()
    
    def _start_debug_terminal(self) -> bool:
        """Start a separate terminal window for debug display"""
        try:
            # Create a temporary script that displays debug info
            script_content = '''#!/bin/bash
# KitchenSync Debug Terminal
echo "🐛 KitchenSync Debug Monitor"
echo "=========================="
echo "Debug information will appear here..."
echo ""

# Create a named pipe for communication
PIPE="/tmp/kitchensync_debug"
mkfifo "$PIPE" 2>/dev/null || true

# Read from pipe and display
while true; do
    if read line <"$PIPE"; then
        echo "$line"
    else
        sleep 0.1
    fi
done
'''
            
            # Write script to temporary file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.sh', delete=False) as f:
                f.write(script_content)
                script_path = f.name
            
            # Make script executable
            os.chmod(script_path, 0o755)
            
            # Try different terminal emulators
            terminal_commands = [
                ['gnome-terminal', '--geometry=60x20+1520+0', '--title=KitchenSync Debug', '--', 'bash', script_path],
                ['xterm', '-geometry', '60x20+1520+0', '-title', 'KitchenSync Debug', '-e', 'bash', script_path],
                ['lxterminal', '--geometry=60x20', '--title=KitchenSync Debug', '-e', 'bash ' + script_path],
            ]
            
            for cmd in terminal_commands:
                try:
                    self.terminal_process = subprocess.Popen(cmd, 
                                                            stdout=subprocess.DEVNULL, 
                                                            stderr=subprocess.DEVNULL)
                    print(f"✓ Debug terminal started with {cmd[0]}")
                    time.sleep(1)  # Give terminal time to start
                    return True
                except Exception:
                    continue
            
            raise DebugError("No suitable terminal emulator found")
            
        except Exception as e:
            print(f"⚠️ Could not start debug terminal: {e}")
            return False
    
    def send_message(self, message: str) -> None:
        """Send a message to the debug terminal"""
        try:
            with open(self.pipe_path, 'w') as pipe:
                pipe.write(f"{message}\n")
                pipe.flush()
        except Exception:
            pass  # Ignore pipe errors
    
    def cleanup(self) -> None:
        """Clean up terminal debugger"""
        try:
            if self.terminal_process:
                self.terminal_process.terminate()
            
            # Clean up the named pipe
            if os.path.exists(self.pipe_path):
                os.unlink(self.pipe_path)
            
            print("✓ Debug terminal cleaned up")
        except Exception as e:
            print(f"⚠️ Debug terminal cleanup error: {e}")


class DebugManager:
    """Manages debug information and overlays"""
    
    def __init__(self, pi_id: str, video_file: str, debug_mode: bool = False):
        self.pi_id = pi_id
        self.video_file = video_file
        self.debug_mode = debug_mode
        self.overlay = None
        self.terminal_debugger = None
        
        if debug_mode:
            self._initialize_debug_display()
    
    def _initialize_debug_display(self) -> None:
        """Initialize appropriate debug display"""
        if self.pi_id == 'leader-pi' or 'leader' in self.pi_id:
            # Use terminal debugger for leader
            try:
                self.terminal_debugger = TerminalDebugger()
            except Exception as e:
                print(f"⚠️ Could not initialize terminal debugger: {e}")
        else:
            # Use overlay for collaborators
            try:
                self.overlay = DebugOverlay(self.pi_id, self.video_file, use_pygame=True)
            except Exception as e:
                print(f"⚠️ Could not initialize debug overlay: {e}")
                try:
                    self.overlay = DebugOverlay(self.pi_id, self.video_file, use_pygame=False)
                except Exception as e2:
                    print(f"⚠️ Could not initialize text debug: {e2}")
    
    def update_display(self, current_time: float = 0, total_time: float = 0, 
                      additional_info: Optional[List[str]] = None) -> None:
        """Update debug display"""
        if not self.debug_mode:
            return
        
        if self.overlay:
            self.overlay.update_display(current_time, total_time, additional_info)
        elif self.terminal_debugger and additional_info:
            # Send first line of additional info to terminal
            message = f"🐛 {self.pi_id} - {current_time:.1f}s"
            if additional_info:
                message += f" | {additional_info[0]}"
            self.terminal_debugger.send_message(message)
    
    def cleanup(self) -> None:
        """Clean up debug resources"""
        if self.overlay:
            self.overlay.cleanup()
        if self.terminal_debugger:
            self.terminal_debugger.cleanup()
