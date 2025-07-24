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
        
        # Display settings - position debug window on left side
        self.overlay_width = 500
        self.overlay_height = 400
        self.overlay_x = 50  # Position to left of video
        self.overlay_y = 50
        
        # State
        self.screen = None
        self.font = None
        self.clock = None
        self.keep_on_top = False
        self.raise_thread = None
        self.update_thread = None
        self.running = False
        self.state_lock = threading.Lock()
        
        # Debug data tracking (shared state)
        self.state = {
            'video_file': video_file,
            'current_time': 0.0,
            'total_time': 0.0,
            'midi_data': None,
            'is_leader': False,
            'pi_id': pi_id
        }
        
        # Initialize overlay
        if self.use_pygame:
            print(f"[DEBUG] Initializing pygame overlay for {self.pi_id} (video: {self.video_file})")
            self._init_pygame_overlay()
            self.running = True
            self.update_thread = threading.Thread(target=self._update_loop, daemon=True)
            self.update_thread.start()
        else:
            print(f"[DEBUG] Text-based debug overlay initialized for {self.pi_id}")
    
    def set_state(self, *, video_file=None, current_time=None, total_time=None, midi_data=None, is_leader=None, pi_id=None):
        with self.state_lock:
            if video_file is not None:
                self.state['video_file'] = video_file
            if current_time is not None:
                self.state['current_time'] = current_time
            if total_time is not None:
                self.state['total_time'] = total_time
            if midi_data is not None:
                self.state['midi_data'] = midi_data
            if is_leader is not None:
                self.state['is_leader'] = is_leader
            if pi_id is not None:
                self.state['pi_id'] = pi_id
    
    def _init_pygame_overlay(self) -> None:
        """Initialize pygame overlay for visual debug display"""
        try:
            # VLC should already be positioned by now
            os.environ['SDL_VIDEO_WINDOW_POS'] = f'{self.overlay_x},{self.overlay_y}'
            
            pygame.init()
            pygame.display.set_caption("KitchenSync Debug")
            
            self.screen = pygame.display.set_mode((self.overlay_width, self.overlay_height))
            self.font = pygame.font.Font(None, 20)  # Smaller font for more info
            self.clock = pygame.time.Clock()
            
            # Set window to stay on top but not interfere with VLC
            self.keep_on_top = True
            self.raise_thread = threading.Thread(target=self._window_raise_loop, daemon=True)
            self.raise_thread.start()
            
            print(f"Pygame debug overlay initialized for {self.pi_id}")
            
        except Exception as e:
            print(f"Pygame overlay init failed: {e}, falling back to text mode")
            self.use_pygame = False
    
    def _window_raise_loop(self) -> None:
        """Keep debug window on top but not too aggressively"""
        while self.keep_on_top:
            try:
                # Use wmctrl to keep window on top, but less frequently
                subprocess.run(['wmctrl', '-r', 'KitchenSync Debug', '-b', 'add,above'], 
                              capture_output=True, timeout=1)
            except Exception:
                pass
            time.sleep(5)  # Check every 5 seconds instead of 2
    
    def _update_loop(self):
        while self.running:
            try:
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        self.running = False
                        return
                with self.state_lock:
                    video_file = self.state['video_file']
                    current_time = self.state['current_time']
                    total_time = self.state['total_time']
                    midi_data = self.state['midi_data']
                    is_leader = self.state['is_leader']
                    pi_id = self.state['pi_id']
                self._draw_overlay(video_file, current_time, total_time, midi_data, is_leader, pi_id)
                self.clock.tick(10)  # 10 FPS
            except Exception as e:
                print(f"[DEBUG] Error in debug overlay update loop: {e}")
                time.sleep(0.5)
    
    def _draw_overlay(self, video_file, current_time, total_time, midi_data, is_leader, pi_id):
        """Update pygame-based visual overlay with fixed display"""
        try:
            # Clear screen with dark background
            self.screen.fill((20, 20, 20))
            
            # Update MIDI data if provided
            if midi_data:
                # The recent, current, upcoming triggers are now part of midi_data
                # No need to re-calculate or store them separately here.
                pass
            
            y_pos = 10
            line_height = 22
            
            # Title
            title_color = (255, 255, 255)
            leader_str = " (LEADER)" if is_leader else ""
            text = self.font.render(f"KitchenSync Debug - Pi {pi_id}{leader_str}", True, title_color)
            self.screen.blit(text, (10, y_pos))
            y_pos += line_height + 5
            
            # Separator line
            pygame.draw.line(self.screen, (100, 100, 100), (10, y_pos), (self.overlay_width - 10, y_pos))
            y_pos += 10
            
            # Video file name
            video_name = os.path.basename(video_file) if video_file else "No video"
            if len(video_name) > 35:
                video_name = video_name[:32] + "..."
            text = self.font.render(f"Video: {video_name}", True, (200, 200, 255))
            self.screen.blit(text, (10, y_pos))
            y_pos += line_height
            
            # Time display
            current_min = int(current_time // 60)
            current_sec = int(current_time % 60)
            total_min = int(total_time // 60) if total_time > 0 else 0
            total_sec = int(total_time % 60) if total_time > 0 else 0
            time_str = f"Time: {current_min:02d}:{current_sec:02d} / {total_min:02d}:{total_sec:02d}"
            text = self.font.render(time_str, True, (100, 255, 100))
            self.screen.blit(text, (10, y_pos))
            y_pos += line_height + 10
            
            # MIDI section header
            text = self.font.render("MIDI Events:", True, (255, 200, 100))
            self.screen.blit(text, (10, y_pos))
            y_pos += line_height
            
            # Past 3 MIDI triggers
            text = self.font.render("Recent triggers:", True, (180, 180, 180))
            self.screen.blit(text, (20, y_pos))
            y_pos += line_height - 5
            
            if midi_data and midi_data.get('recent'):
                for i, trigger in enumerate(midi_data['recent'][-3:]):
                    trigger_str = self._format_midi_event(trigger)
                    text = self.font.render(f"  {i+1}. {trigger_str}", True, (150, 150, 150))
                    self.screen.blit(text, (20, y_pos))
                    y_pos += line_height - 3
            else:
                text = self.font.render("  None", True, (100, 100, 100))
                self.screen.blit(text, (20, y_pos))
                y_pos += line_height - 3
            
            y_pos += 5
            
            # Current/most recent MIDI trigger (highlighted in yellow)
            text = self.font.render("Current trigger:", True, (180, 180, 180))
            self.screen.blit(text, (20, y_pos))
            y_pos += line_height - 5
            
            if midi_data and midi_data.get('current'):
                trigger_str = self._format_midi_event(midi_data['current'])
                text = self.font.render(f"  -> {trigger_str}", True, (255, 255, 100))  # Yellow
                self.screen.blit(text, (20, y_pos))
            else:
                text = self.font.render("  None", True, (100, 100, 100))
                self.screen.blit(text, (20, y_pos))
            y_pos += line_height + 5
            
            # Upcoming 3 MIDI triggers
            text = self.font.render("Upcoming triggers:", True, (180, 180, 180))
            self.screen.blit(text, (20, y_pos))
            y_pos += line_height - 5
            
            if midi_data and midi_data.get('upcoming'):
                for i, trigger in enumerate(midi_data['upcoming'][:3]):
                    trigger_str = self._format_midi_event(trigger)
                    time_until = trigger.get('time', 0) - current_time
                    if time_until > 0:
                        trigger_str += f" (in {time_until:.1f}s)"
                    text = self.font.render(f"  {i+1}. {trigger_str}", True, (200, 255, 200))
                    self.screen.blit(text, (20, y_pos))
                    y_pos += line_height - 3
            else:
                text = self.font.render("  None", True, (100, 100, 100))
                self.screen.blit(text, (20, y_pos))
            
            pygame.display.flip()
            
        except Exception as e:
            print(f"Error updating pygame overlay: {e}")
    
    def _format_midi_event(self, event: Dict[str, Any]) -> str:
        """Format MIDI event for display"""
        if not event:
            return "Unknown"
        
        event_type = event.get('type', 'unknown')
        time_val = event.get('time', 0)
        
        if event_type == 'note_on':
            note = event.get('note', 0)
            channel = event.get('channel', 1)
            velocity = event.get('velocity', 127)
            return f"{time_val:.1f}s: Note ON Ch{channel} N{note} V{velocity}"
        elif event_type == 'note_off':
            note = event.get('note', 0)
            channel = event.get('channel', 1)
            return f"{time_val:.1f}s: Note OFF Ch{channel} N{note}"
        elif event_type == 'control_change':
            control = event.get('control', 0)
            value = event.get('value', 0)
            channel = event.get('channel', 1)
            return f"{time_val:.1f}s: CC Ch{channel} C{control} V{value}"
        else:
            return f"{time_val:.1f}s: {event_type}"
    
    def cleanup(self) -> None:
        """Clean up overlay resources"""
        self.running = False
        if self.use_pygame:
            try:
                # Stop the window raising thread
                self.keep_on_top = False
                if self.raise_thread:
                    self.raise_thread.join(timeout=1)
                if self.update_thread:
                    self.update_thread.join(timeout=1)
                
                pygame.quit()
                print(f"[DEBUG] ✓ Pygame debug overlay cleaned up for {self.pi_id}")
            except Exception as e:
                print(f"[DEBUG] Error cleaning up pygame overlay: {e}")


# TERMINAL DEBUGGER DISABLED - ONLY PYGAME OVERLAY USED
# class TerminalDebugger:
#     """Terminal-based debug display for leader"""
#     
#     def __init__(self):
#         pass  # Disabled
#     
#     def _start_debug_terminal(self) -> bool:
#         pass  # Disabled
#     
#     def send_message(self, message: str) -> None:
#         pass  # Disabled
#     
#     def cleanup(self) -> None:
#         pass  # Disabled


class DebugManager:
    """Manages debug information and overlays"""
    _overlay_created = False  # Class-level guard to prevent duplicate overlays
    
    def __init__(self, pi_id: str, video_file: str, debug_mode: bool = False):
        self.pi_id = pi_id
        self.video_file = video_file
        self.debug_mode = debug_mode
        self.overlay = None
        self.terminal_debugger = None
        
        print(f"[DEBUG] DebugManager init: PID={os.getpid()}, pi_id={pi_id}, debug_mode={debug_mode}, video_file={video_file}")
        
        if debug_mode:
            self._initialize_debug_display()
    
    def _initialize_debug_display(self) -> None:
        """Initialize appropriate debug display (idempotent - only creates once)"""
        print(f"[DEBUG] Initializing debug display for: {self.pi_id}")
        
        # GUARD: Only initialize once - prevent multiple window creation
        if self.overlay is not None or DebugManager._overlay_created:
            print(f"[DEBUG] Debug display already initialized for {self.pi_id} - skipping")
            return
        
        # ALWAYS use pygame overlay - no terminal debugger ever
        print(f"[DEBUG] Creating pygame overlay for Pi: {self.pi_id}")
        try:
            self.overlay = DebugOverlay(self.pi_id, self.video_file, use_pygame=True)
            DebugManager._overlay_created = True
            print(f"[DEBUG] SUCCESS: Pygame overlay created for Pi: {self.pi_id}")
        except Exception as e:
            print(f"[DEBUG] FAILED pygame overlay: {e}")
            # Fall back to text mode if pygame fails
            try:
                self.overlay = DebugOverlay(self.pi_id, self.video_file, use_pygame=False)
                DebugManager._overlay_created = True
                print(f"[DEBUG] SUCCESS: Text debug fallback for Pi: {self.pi_id}")
            except Exception as e2:
                print(f"[DEBUG] FAILED: Could not initialize any debug display: {e2}")
                    
        print(f"[DEBUG] Debug initialization complete. overlay={self.overlay is not None}, terminal=False")
    
    def update_display(self, current_time: float = 0, total_time: float = 0, 
                      midi_data: Optional[Dict[str, Any]] = None) -> None:
        """Update debug display with MIDI information"""
        if not self.debug_mode:
            return
        
        # Debug: Print data flow every 5 seconds
        if int(current_time) % 5 == 0 and current_time > 0:
            print(f"DEBUG UPDATE: time={current_time:.1f}, total={total_time:.1f}, midi_events={len(midi_data.get('recent', [])) if midi_data else 0}")
        
        # Only use overlay - terminal debugger is disabled
        if self.overlay:
            self.overlay.set_state(current_time=current_time, total_time=total_time, midi_data=midi_data)
        else:
            print(f"WARNING: No debug overlay available for update at {current_time:.1f}s")
    
    def _format_midi_event_simple(self, event: Dict[str, Any]) -> str:
        """Simple MIDI event formatting for terminal"""
        if not event:
            return "Unknown"
        
        event_type = event.get('type', 'unknown')
        time_val = event.get('time', 0)
        
        if event_type == 'note_on':
            note = event.get('note', 0)
            channel = event.get('channel', 1)
            return f"{time_val:.1f}s: Note ON Ch{channel} N{note}"
        elif event_type == 'note_off':
            note = event.get('note', 0)
            channel = event.get('channel', 1)
            return f"{time_val:.1f}s: Note OFF Ch{channel} N{note}"
        else:
            return f"{time_val:.1f}s: {event_type}"
    
    def cleanup(self) -> None:
        """Clean up debug resources"""
        if self.overlay:
            print(f"[DEBUG] Cleaning up debug overlay for {self.pi_id}")
            self.overlay.cleanup()
            DebugManager._overlay_created = False
        # Terminal debugger is disabled
        # if self.terminal_debugger:
        #     self.terminal_debugger.cleanup()
