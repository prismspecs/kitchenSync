#!/usr/bin/env python3
"""
Core System State Management for kSync
Manages system state and provides status information
"""

import time
from typing import Dict, Any, Optional, List
from collections import deque


class SystemState:
    """Manages system state and timing information"""

    def __init__(self):
        self.is_running = False
        self.start_time: Optional[float] = None
        self.current_time = 0.0
        self.last_update = 0.0

        # Statistics
        self.stats = {
            "sessions_started": 0,
            "total_runtime": 0.0,
            "last_session_duration": 0.0,
        }

    def start_session(self) -> None:
        """Start a new session"""
        if self.is_running:
            self.stop_session()

        self.start_time = time.time()
        self.is_running = True
        self.stats["sessions_started"] += 1
        print(f" Session started at {time.strftime('%H:%M:%S')}")

    def stop_session(self) -> None:
        """Stop the current session"""
        if self.is_running and self.start_time:
            session_duration = time.time() - self.start_time
            self.stats["total_runtime"] += session_duration
            self.stats["last_session_duration"] = session_duration
            print(f" Session ended (duration: {session_duration:.1f}s)")

        self.is_running = False
        self.start_time = None
        self.current_time = 0.0

    @property
    def is_syncing(self) -> bool:
        """Check if system is currently in a running/syncing state"""
        return self.is_running

    def get(self, key: str, default: Any = None) -> Any:
        """
        Safety fallback for code treating SystemState as a dictionary.
        Logs the access to help identify the caller.
        """
        from core.logger import log_warning
        log_warning(f"SystemState: Legacy dictionary-style access detected for key '{key}'")
        
        # Try to return matching attribute if it exists
        if hasattr(self, key):
            return getattr(self, key)
            
        return default

    def update_time(self) -> float:
        """Update current time and return it"""
        if self.is_running and self.start_time:
            self.current_time = time.time() - self.start_time
            self.last_update = time.time()
        return self.current_time

    def get_elapsed_time(self) -> float:
        """Get elapsed time since session start"""
        return self.current_time

    def get_formatted_time(self) -> str:
        """Get formatted time display"""
        minutes = int(self.current_time // 60)
        seconds = int(self.current_time % 60)
        return f"{minutes:02d}:{seconds:02d}"

    def get_stats(self) -> Dict[str, Any]:
        """Get system statistics"""
        return self.stats.copy()
