#!/usr/bin/env python3
"""
Core System State Management for KitchenSync
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
        print(f"🚀 Session started at {time.strftime('%H:%M:%S')}")

    def stop_session(self) -> None:
        """Stop the current session"""
        if self.is_running and self.start_time:
            session_duration = time.time() - self.start_time
            self.stats["total_runtime"] += session_duration
            self.stats["last_session_duration"] = session_duration
            print(f"🛑 Session ended (duration: {session_duration:.1f}s)")

        self.is_running = False
        self.start_time = None
        self.current_time = 0.0

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


class CollaboratorRegistry:
    """Manages registered collaborator Pis"""

    def __init__(self, timeout: float = 10.0):
        self.collaborators: Dict[str, Dict[str, Any]] = {}
        self.timeout = timeout

    def register_collaborator(
        self, device_id: str, ip: str, status: str = "ready", video_file: str = ""
    ) -> None:
        """Register a new collaborator or update existing one"""
        self.collaborators[device_id] = {
            "ip": ip,
            "status": status,
            "video_file": video_file,
            "last_seen": time.time(),
            "registered_at": time.time(),
        }
        print(f"✓ Registered collaborator: {device_id} at {ip}")

    def update_heartbeat(self, device_id: str, status: str = "ready") -> None:
        """Update collaborator heartbeat"""
        if device_id in self.collaborators:
            self.collaborators[device_id]["last_seen"] = time.time()
            self.collaborators[device_id]["status"] = status

    def remove_collaborator(self, device_id: str) -> None:
        """Remove a collaborator"""
        if device_id in self.collaborators:
            del self.collaborators[device_id]
            print(f"🗑️ Removed collaborator: {device_id}")

    def get_collaborators(self) -> Dict[str, Dict[str, Any]]:
        """Get all collaborators with online status"""
        current_time = time.time()
        result = {}

        for device_id, info in self.collaborators.items():
            info_copy = info.copy()
            last_seen = current_time - info["last_seen"]
            info_copy["online"] = last_seen < self.timeout
            info_copy["last_seen_seconds"] = last_seen
            result[device_id] = info_copy

        return result

    def get_online_collaborators(self) -> Dict[str, Dict[str, Any]]:
        """Get only online collaborators"""
        all_collaborators = self.get_collaborators()
        return {
            device_id: info
            for device_id, info in all_collaborators.items()
            if info["online"]
        }

    def get_collaborator_count(self) -> int:
        """Get total number of registered collaborators"""
        return len(self.collaborators)

    def get_online_count(self) -> int:
        """Get number of online collaborators"""
        return len(self.get_online_collaborators())

    def cleanup_stale_collaborators(self) -> None:
        """Remove collaborators that haven't been seen for a long time"""
        current_time = time.time()
        stale_devices = []

        for device_id, info in self.collaborators.items():
            if current_time - info["last_seen"] > self.timeout * 3:  # 3x timeout
                stale_devices.append(device_id)

        for device_id in stale_devices:
            self.remove_collaborator(device_id)


class SyncTracker:
    """Tracks synchronization quality and drift"""

    def __init__(self, max_samples: int = 50):
        self.max_samples = max_samples
        self.sync_samples = deque(maxlen=max_samples)
        self.last_sync_time = 0.0
        self.drift_history = deque(maxlen=max_samples)

    def record_sync(self, leader_time: float, local_time: float) -> None:
        """Record a sync point"""
        self.last_sync_time = time.time()

        if self.sync_samples:
            # Calculate drift from expected time
            expected_time = self.sync_samples[-1]["leader_time"] + (
                local_time - self.sync_samples[-1]["local_time"]
            )
            drift = leader_time - expected_time
            self.drift_history.append(drift)

        self.sync_samples.append(
            {
                "leader_time": leader_time,
                "local_time": local_time,
                "timestamp": self.last_sync_time,
            }
        )

    def get_average_drift(self) -> float:
        """Get average drift over recent samples"""
        if not self.drift_history:
            return 0.0
        return sum(self.drift_history) / len(self.drift_history)

    def get_sync_quality(self) -> str:
        """Get sync quality assessment"""
        if not self.sync_samples:
            return "No sync data"

        time_since_sync = time.time() - self.last_sync_time

        if time_since_sync > 10:
            return "Sync lost"
        elif time_since_sync > 5:
            return "Sync degraded"
        else:
            avg_drift = abs(self.get_average_drift())
            if avg_drift < 0.1:
                return "Excellent"
            elif avg_drift < 0.5:
                return "Good"
            elif avg_drift < 1.0:
                return "Fair"
            else:
                return "Poor"

    def is_synced(self, timeout: float = 5.0) -> bool:
        """Check if currently synced"""
        return time.time() - self.last_sync_time < timeout

    def get_stats(self) -> Dict[str, Any]:
        """Get sync statistics"""
        return {
            "sample_count": len(self.sync_samples),
            "average_drift": self.get_average_drift(),
            "sync_quality": self.get_sync_quality(),
            "last_sync": self.last_sync_time,
            "is_synced": self.is_synced(),
        }
