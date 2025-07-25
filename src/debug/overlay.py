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
    """Debug overlay system with file-based output for Pi services"""
    
    def __init__(self, pi_id: str, video_file: str, use_pygame: bool = True):
        self.pi_id = pi_id
        self.video_file = video_file
        
        # For systemd services, always use file-based debug
        self.use_file_debug = True
        self.debug_file = f"/tmp/kitchensync_debug_{pi_id}.txt"
        
        # State tracking
        self.state_lock = threading.Lock()
        self.last_update_time = 0
        
        # Debug data tracking (shared state)
        self.state = {
            'video_file': video_file,
            'current_time': 0.0,
            'total_time': 0.0,
            'midi_data': None,
            'is_leader': False,
            'pi_id': pi_id
        }
        
        # Initialize file-based debug
        self._init_file_debug()
        print(f"[DEBUG] File-based debug initialized for {self.pi_id} -> {self.debug_file}")
    
    def _init_file_debug(self):
        """Initialize file-based debug output"""
        try:
            with open(self.debug_file, 'w') as f:
                f.write(f"KitchenSync Debug - Pi {self.pi_id}\n")
                f.write("=" * 50 + "\n")
                f.write(f"Started at: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Video: {os.path.basename(self.video_file) if self.video_file else 'No video'}\n")
                f.write("=" * 50 + "\n\n")
            print(f"[DEBUG] Debug file created: {self.debug_file}")
            print(f"[DEBUG] Monitor with: tail -f {self.debug_file}")
        except Exception as e:
            print(f"[DEBUG] Error creating debug file: {e}")
    
    def set_state(self, *, video_file=None, current_time=None, total_time=None, midi_data=None, is_leader=None, pi_id=None):
        with self.state_lock:
            updated_fields = []
            significant_change = False
            
            if video_file is not None and video_file != self.state.get('video_file'):
                self.state['video_file'] = video_file
                updated_fields.append(f"video_file={video_file}")
                significant_change = True
                
            if current_time is not None:
                old_time = self.state.get('current_time', 0)
                if abs(current_time - old_time) >= 1.0:  # Only log time changes of 1+ seconds
                    self.state['current_time'] = current_time
                    updated_fields.append(f"current_time={current_time:.1f}")
                    significant_change = True
                else:
                    self.state['current_time'] = current_time  # Update silently
                    
            if total_time is not None and total_time != self.state.get('total_time'):
                self.state['total_time'] = total_time
                updated_fields.append(f"total_time={total_time:.1f}")
                significant_change = True
                
            if midi_data is not None:
                self.state['midi_data'] = midi_data
                # Only log MIDI changes if there are actual events
                if midi_data.get('current') or midi_data.get('recent') or midi_data.get('upcoming'):
                    updated_fields.append(f"midi_data={len(midi_data.get('recent', []))} recent, {len(midi_data.get('upcoming', []))} upcoming")
                    significant_change = True
                    
            if is_leader is not None and is_leader != self.state.get('is_leader'):
                self.state['is_leader'] = is_leader
                updated_fields.append(f"is_leader={is_leader}")
                significant_change = True
                
            if pi_id is not None and pi_id != self.state.get('pi_id'):
                self.state['pi_id'] = pi_id
                updated_fields.append(f"pi_id={pi_id}")
                significant_change = True
            
            # Only log if there are significant changes
            if updated_fields and significant_change:
                print(f"[DEBUG] set_state: {', '.join(updated_fields)}")
            
            # Update file every 5 seconds or on significant changes
            now = time.time()
            if significant_change or (now - self.last_update_time) > 5:
                self._update_file_debug()
                self.last_update_time = now
    
    def _update_file_debug(self):
        """Update the debug file with current state"""
        try:
            with self.state_lock:
                video_file = self.state['video_file']
                current_time = self.state['current_time']
                total_time = self.state['total_time']
                midi_data = self.state['midi_data']
                is_leader = self.state['is_leader']
                pi_id = self.state['pi_id']
            
            # Format time
            current_min = int(current_time // 60)
            current_sec = int(current_time % 60)
            total_min = int(total_time // 60) if total_time > 0 else 0
            total_sec = int(total_time % 60) if total_time > 0 else 0
            time_str = f"{current_min:02d}:{current_sec:02d} / {total_min:02d}:{total_sec:02d}"
            
            video_name = os.path.basename(video_file) if video_file else "No video"
            leader_str = " (LEADER)" if is_leader else ""
            
            debug_content = []
            debug_content.append(f"[{time.strftime('%H:%M:%S')}] KitchenSync Debug - Pi {pi_id}{leader_str}")
            debug_content.append(f"Video: {video_name}")
            debug_content.append(f"Time: {time_str}")
            debug_content.append("")
            
            if midi_data:
                debug_content.append("MIDI Events:")
                
                # Recent events
                recent = midi_data.get('recent', [])
                if recent:
                    debug_content.append("  Recent:")
                    for i, event in enumerate(recent[-3:]):
                        event_str = self._format_midi_event(event)
                        debug_content.append(f"    {i+1}. {event_str}")
                else:
                    debug_content.append("  Recent: None")
                
                # Current event
                current = midi_data.get('current')
                if current:
                    event_str = self._format_midi_event(current)
                    debug_content.append(f"  Current: -> {event_str}")
                else:
                    debug_content.append("  Current: None")
                
                # Upcoming events
                upcoming = midi_data.get('upcoming', [])
                if upcoming:
                    debug_content.append("  Upcoming:")
                    for i, event in enumerate(upcoming[:3]):
                        event_str = self._format_midi_event(event)
                        time_until = event.get('time', 0) - current_time
                        if time_until > 0:
                            event_str += f" (in {time_until:.1f}s)"
                        debug_content.append(f"    {i+1}. {event_str}")
                else:
                    debug_content.append("  Upcoming: None")
            else:
                debug_content.append("MIDI Events: No data")
            
            debug_content.append("=" * 50)
            debug_content.append("")
            
            # Write to file
            with open(self.debug_file, 'a') as f:
                f.write('\n'.join(debug_content))
            
        except Exception as e:
            print(f"[DEBUG] Error updating debug file: {e}")
    
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
        try:
            with open(self.debug_file, 'a') as f:
                f.write(f"\n[{time.strftime('%H:%M:%S')}] Debug session ended\n")
                f.write("=" * 50 + "\n")
            print(f"[DEBUG] ✓ File debug cleaned up for {self.pi_id}")
        except Exception as e:
            print(f"[DEBUG] Error cleaning up debug file: {e}")


class DebugManager:
    """Manages debug information and overlays"""
    
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
        """Initialize appropriate debug display"""
        print(f"[DEBUG] Initializing file-based debug for: {self.pi_id}")
        
        # GUARD: Only initialize once per manager instance
        if self.overlay is not None:
            print(f"[DEBUG] Debug display already initialized for {self.pi_id} - skipping")
            return
        
        print(f"[DEBUG] Creating file-based debug for Pi: {self.pi_id}")
        try:
            self.overlay = DebugOverlay(self.pi_id, self.video_file, use_pygame=False)
            print(f"[DEBUG] SUCCESS: File-based debug created for Pi: {self.pi_id}")
            print(f"[DEBUG] Monitor with: ssh kitchensync@192.168.178.59 'tail -f /tmp/kitchensync_debug_{self.pi_id}.txt'")
        except Exception as e:
            print(f"[DEBUG] FAILED: Could not initialize debug display: {e}")
                    
        print(f"[DEBUG] Debug initialization complete. overlay={self.overlay is not None}")
    
    def update_display(self, current_time: float = 0, total_time: float = 0, 
                      midi_data: Optional[Dict[str, Any]] = None) -> None:
        """Update debug display with MIDI information"""
        if not self.debug_mode:
            return
        
        # Only use overlay
        if self.overlay:
            self.overlay.set_state(current_time=current_time, total_time=total_time, midi_data=midi_data)
        else:
            print(f"WARNING: No debug overlay available for update at {current_time:.1f}s")
    
    def cleanup(self) -> None:
        """Clean up debug resources"""
        if self.overlay:
            print(f"[DEBUG] Cleaning up debug overlay for {self.pi_id}")
            self.overlay.cleanup()
