#!/usr/bin/env python3
"""
Simple pygame debug overlay for Pi display with automatic fallback
"""

import pygame
import threading
import time
import os
from typing import Optional, Dict, Any
from core.logger import log_info, log_warning, log_error, snapshot_env, log_file_paths


class SimpleDebugOverlay:
    """Simple debug overlay that displays on the Pi's screen or falls back to file"""

    def __init__(self, pi_id: str):
        self.pi_id = pi_id
        self.running = True
        self.state_lock = threading.Lock()
        self.use_pygame = False
        self.screen = None

        # Initialize state
        self.state = {
            "video_file": "No video",
            "current_time": 0.0,
            "total_time": 0.0,
            "session_time": 0.0,
            "video_position": None,
            "midi_current": None,
            "midi_next": None,
            "is_leader": False,
        }

        # Try pygame first, fall back to file if it fails
        try:
            # Check if we have a display
            if not os.environ.get("DISPLAY") and not os.environ.get("SDL_VIDEODRIVER"):
                raise Exception("No display available")

            # Force software rendering and disable OpenGL completely
            os.environ["SDL_VIDEODRIVER"] = "x11"
            os.environ["SDL_VIDEO_GL"] = "0"
            os.environ["SDL_VIDEO_OPENGL"] = "0"
            os.environ["SDL_VIDEO_OPENGL_ES"] = "0"
            os.environ["SDL_VIDEO_OPENGL_ES2"] = "0"
            os.environ["SDL_VIDEO_VULKAN"] = "0"
            os.environ["SDL_VIDEO_METAL"] = "0"

            pygame.init()
            pygame.font.init()
            pygame.display.init()

            # Try different display drivers if the first fails
            display_drivers = ["x11", "drm", "kmsdrm", "wayland"]
            display_initialized = False

            for driver in display_drivers:
                try:
                    os.environ["SDL_VIDEODRIVER"] = driver
                    pygame.display.init()
                    display_initialized = True
                    log_info(
                        f"Display initialized with driver: {driver}",
                        component="overlay",
                    )
                    break
                except Exception as e:
                    log_warning(f"Driver {driver} failed: {e}", component="overlay")
                    continue

            if not display_initialized:
                raise Exception("No display driver could be initialized")

            # Determine desktop size for safe placement (before setting window)
            overlay_width = 400
            overlay_height = 300
            try:
                desktop_sizes = pygame.display.get_desktop_sizes()
                if desktop_sizes and len(desktop_sizes) > 0:
                    desktop_w, desktop_h = desktop_sizes[0]
                else:
                    info = pygame.display.Info()
                    desktop_w, desktop_h = info.current_w, info.current_h
            except Exception:
                desktop_w, desktop_h = 1920, 1080

            # Place overlay near top-left to avoid video window (which we push to right in debug mode)
            pos_x = 50
            pos_y = 50
            if pos_x + overlay_width > desktop_w:
                pos_x = max(0, desktop_w - overlay_width - 10)
            if pos_y + overlay_height > desktop_h:
                pos_y = max(0, desktop_h - overlay_height - 10)

            # IMPORTANT: set position before creating the window
            os.environ["SDL_VIDEO_WINDOW_POS"] = f"{pos_x},{pos_y}"

            # Create a small overlay window with minimal flags
            self.width = overlay_width
            self.height = overlay_height
            # Use only software rendering, no double buffering or resizing
            flags = pygame.SWSURFACE
            self.screen = pygame.display.set_mode((self.width, self.height), flags)
            pygame.display.set_caption(f"KitchenSync Debug - {pi_id}")

            # Fonts
            self.font_large = pygame.font.Font(None, 24)
            self.font_medium = pygame.font.Font(None, 20)
            self.font_small = pygame.font.Font(None, 16)

            # Colors
            self.bg_color = (20, 20, 30)  # Dark blue
            self.text_color = (255, 255, 255)  # White
            self.highlight_color = (100, 200, 255)  # Light blue
            self.leader_color = (255, 200, 100)  # Yellow/orange

            self.use_pygame = True
            log_info(
                f"Pygame overlay initialized at {pos_x},{pos_y} ({self.width}x{self.height})",
                component="overlay",
            )

            # Start the display loop
            self.display_thread = threading.Thread(
                target=self._display_loop, daemon=True
            )
            self.display_thread.start()

        except Exception as e:
            log_warning(f"Pygame failed ({e}), using file debug", component="overlay")
            self.use_pygame = False
            self.screen = None

            # Set up file-based debug
            self.debug_file = f"/tmp/kitchensync_debug_{pi_id}.txt"
            try:
                with open(self.debug_file, "w") as f:
                    f.write(f"KitchenSync Debug - {pi_id}\n")
                    f.write("=" * 40 + "\n")
                    f.write(f"Started: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                    f.write("(Pygame not available - using file debug)\n")
                    f.write("=" * 40 + "\n\n")
                log_info(
                    f"File debug initialized: {self.debug_file}", component="overlay"
                )
            except Exception as file_error:
                log_error(f"File debug also failed: {file_error}", component="overlay")

    def update_state(self, **kwargs):
        """Update the debug state"""
        with self.state_lock:
            self.state.update(kwargs)

        # If using file debug, write update immediately
        if not self.use_pygame and hasattr(self, "debug_file"):
            self._write_file_debug()

    def _display_loop(self):
        """Main display loop for pygame"""
        if not self.use_pygame or not self.screen:
            return

        clock = pygame.time.Clock()
        error_count = 0
        max_errors = 5  # Give it more chances

        while self.running and self.screen:
            try:
                # Handle pygame events
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        self.running = False

                # Clear screen
                self.screen.fill(self.bg_color)

                # Draw debug info
                self._draw_debug_info()

                # Update display - use update() instead of flip() for software rendering
                pygame.display.update()
                clock.tick(10)  # Lower FPS for software rendering

                # Reset error count on successful frame
                error_count = 0

            except Exception as e:
                error_count += 1
                log_warning(
                    f"Display loop error ({error_count}/{max_errors}): {e}",
                    component="overlay",
                )

                # If we get persistent display errors, fall back to file debug
                if (
                    error_count >= max_errors
                    or "GL context" in str(e)
                    or "BadAccess" in str(e)
                    or "OpenGL" in str(e)
                ):
                    log_warning(
                        "Switching to file debug due to persistent display errors",
                        component="overlay",
                    )
                    self.use_pygame = False
                    self._init_file_fallback()
                    break

                # Wait a bit before retrying
                time.sleep(2)

    def _init_file_fallback(self):
        """Initialize file debug as fallback"""
        self.debug_file = f"/tmp/kitchensync_debug_{self.pi_id}.txt"
        try:
            with open(self.debug_file, "w") as f:
                f.write(f"KitchenSync Debug - {self.pi_id}\n")
                f.write("=" * 40 + "\n")
                f.write(f"Started: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write("(Switched to file debug due to display issues)\n")
                f.write("=" * 40 + "\n\n")
            log_info(
                f"File debug fallback initialized: {self.debug_file}",
                component="overlay",
            )
        except Exception as e:
            log_error(f"File fallback failed: {e}", component="overlay")

    def _write_file_debug(self):
        """Write current state to file"""
        if not hasattr(self, "debug_file"):
            return

        try:
            with self.state_lock:
                state = self.state.copy()

            # Format time
            current_time = state["current_time"]
            total_time = state["total_time"]
            current_min = int(current_time // 60)
            current_sec = int(current_time % 60)
            total_min = int(total_time // 60) if total_time > 0 else 0
            total_sec = int(total_time % 60) if total_time > 0 else 0
            time_str = (
                f"{current_min:02d}:{current_sec:02d} / {total_min:02d}:{total_sec:02d}"
            )

            video_name = (
                os.path.basename(state["video_file"])
                if state["video_file"]
                else "No video"
            )
            leader_str = " (LEADER)" if state["is_leader"] else ""

            with open(self.debug_file, "a") as f:
                timestamp = time.strftime("%H:%M:%S")
                f.write(f"[{timestamp}] KitchenSync {self.pi_id}{leader_str}\n")
                f.write(f"  Video: {video_name}\n")
                f.write(f"  Time: {time_str}\n")
                f.write(
                    f"  Session: {state['session_time']:.1f}s, Video pos: {state['video_position'] or 'N/A'}\n"
                )

                if state["midi_current"]:
                    midi = state["midi_current"]
                    f.write(
                        f"  Current MIDI: {midi.get('type', 'unknown')} Ch{midi.get('channel', 1)}\n"
                    )

                if state["midi_next"]:
                    midi = state["midi_next"]
                    f.write(
                        f"  Next MIDI: {midi.get('type', 'unknown')} in {midi.get('time_until', 0):.1f}s\n"
                    )

                f.write("  " + "-" * 30 + "\n")
                f.flush()

        except Exception as e:
            log_error(f"File write error: {e}", component="overlay")

    def _draw_debug_info(self):
        """Draw the debug information (pygame only)"""
        if not self.screen or not self.use_pygame:
            return

        y_pos = 10
        line_height = 25

        with self.state_lock:
            state = self.state.copy()

        # Title
        title = f"KitchenSync {self.pi_id}"
        if state["is_leader"]:
            title += " (LEADER)"
            title_surface = self.font_large.render(title, True, self.leader_color)
        else:
            title_surface = self.font_large.render(title, True, self.highlight_color)

        self.screen.blit(title_surface, (10, y_pos))
        y_pos += line_height + 10

        # Video info
        video_name = (
            os.path.basename(state["video_file"]) if state["video_file"] else "No video"
        )
        video_surface = self.font_medium.render(
            f"Video: {video_name}", True, self.text_color
        )
        self.screen.blit(video_surface, (10, y_pos))
        y_pos += line_height

        # Time info
        current_time = state["current_time"]
        total_time = state["total_time"]

        current_min = int(current_time // 60)
        current_sec = int(current_time % 60)
        total_min = int(total_time // 60) if total_time > 0 else 0
        total_sec = int(total_time % 60) if total_time > 0 else 0

        time_str = f"Time: {current_min:02d}:{current_sec:02d} / {total_min:02d}:{total_sec:02d}"
        time_surface = self.font_medium.render(time_str, True, self.highlight_color)
        self.screen.blit(time_surface, (10, y_pos))
        y_pos += line_height

        # Technical info (smaller)
        session_time = state["session_time"]
        video_pos = state["video_position"]
        tech_str = (
            f"Session: {session_time:.1f}s, Video: {video_pos:.1f}s"
            if video_pos
            else f"Session: {session_time:.1f}s"
        )
        tech_surface = self.font_small.render(tech_str, True, (180, 180, 180))
        self.screen.blit(tech_surface, (10, y_pos))
        y_pos += line_height + 10

        # MIDI info
        midi_title = self.font_medium.render("MIDI Events:", True, self.text_color)
        self.screen.blit(midi_title, (10, y_pos))
        y_pos += line_height

        if state["midi_current"]:
            current_midi = state["midi_current"]
            midi_str = f"Current: {current_midi.get('type', 'unknown')} Ch{current_midi.get('channel', 1)}"
            midi_surface = self.font_small.render(midi_str, True, (100, 255, 100))
            self.screen.blit(midi_surface, (10, y_pos))
            y_pos += 20

        if state["midi_next"]:
            next_midi = state["midi_next"]
            next_str = f"Next: {next_midi.get('type', 'unknown')} in {next_midi.get('time_until', 0):.1f}s"
            next_surface = self.font_small.render(next_str, True, (255, 255, 100))
            self.screen.blit(next_surface, (10, y_pos))
            y_pos += 20

        if not state["midi_current"] and not state["midi_next"]:
            no_midi = self.font_small.render(
                "No active MIDI events", True, (128, 128, 128)
            )
            self.screen.blit(no_midi, (10, y_pos))

        # Timestamp
        timestamp = time.strftime("%H:%M:%S")
        timestamp_surface = self.font_small.render(
            f"Updated: {timestamp}", True, (128, 128, 128)
        )
        self.screen.blit(timestamp_surface, (10, self.height - 25))

    def cleanup(self):
        """Clean up resources"""
        self.running = False
        if hasattr(self, "display_thread"):
            self.display_thread.join(timeout=1)

        if self.screen and self.use_pygame:
            pygame.quit()

        if hasattr(self, "debug_file"):
            try:
                with open(self.debug_file, "a") as f:
                    f.write(f"\n[{time.strftime('%H:%M:%S')}] Debug overlay cleanup\n")
                    f.write("=" * 40 + "\n")
            except:
                pass

        log_info("Simple overlay cleaned up", component="overlay")


class SimpleDebugManager:
    """Manages the simple debug overlay"""

    def __init__(self, pi_id: str, is_leader: bool = False):
        self.pi_id = pi_id
        self.is_leader = is_leader
        self.overlay = None

        try:
            self.overlay = SimpleDebugOverlay(pi_id)
            self.overlay.update_state(is_leader=is_leader)
            print(f"[DEBUG] Simple debug manager created for {pi_id}")
        except Exception as e:
            print(f"[DEBUG] Error creating debug manager: {e}")
            self.overlay = None

    def update_debug_info(
        self,
        video_file: str,
        current_time: float,
        total_time: float,
        session_time: float,
        video_position: Optional[float],
        current_cues: list,
        upcoming_cues: list,
    ):
        """Update debug information"""
        if not self.overlay:
            return

        # Process MIDI info
        midi_current = current_cues[0] if current_cues else None
        midi_next = None

        if upcoming_cues:
            next_cue = upcoming_cues[0]
            time_until = next_cue.get("time", 0) - current_time
            midi_next = {
                "type": next_cue.get("type", "unknown"),
                "channel": next_cue.get("channel", 1),
                "time_until": time_until,
            }

        self.overlay.update_state(
            video_file=video_file,
            current_time=current_time,
            total_time=total_time,
            session_time=session_time,
            video_position=video_position,
            midi_current=midi_current,
            midi_next=midi_next,
        )

    def cleanup(self):
        """Clean up resources"""
        if self.overlay:
            self.overlay.cleanup()
            self.overlay = None
