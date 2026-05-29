#!/usr/bin/env python3
"""
Networking Components for kSync
Handles time sync and command communication between leader and collaborators
"""

import json
import socket
import threading
import time
from typing import Callable, Optional, Dict, Any
from core.logger import log_info


UDP_MAX_DATAGRAM_SIZE = 65535


class NetworkError(Exception):
    """Raised when network operations fail"""

    pass


def _get_broadcast_address():
    """Get appropriate broadcast address, prioritizing local subnet broadcast"""
    try:
        # Get local IP to determine network
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Doesn't need to connect, just needs to pick an interface
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()

        # Calculate broadcast for common /24 network
        ip_parts = local_ip.split(".")
        if len(ip_parts) == 4:
            broadcast = f"{ip_parts[0]}.{ip_parts[1]}.{ip_parts[2]}.255"
            return broadcast
    except Exception:
        pass

    # Fallback: Try standard broadcast
    try:
        test_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        test_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        test_sock.close()
        return "255.255.255.255"
    except Exception:
        return "192.168.1.255" # Final sane default


class SyncBroadcaster:
    """Handles time sync broadcasting for leader"""

    def __init__(self, sync_port: int = 5005, tick_interval: float = 0.1, broadcast_ip: Optional[str] = None):
        self.sync_port = sync_port
        # Clamp to a safe range to avoid CPU burn or sluggish updates
        try:
            self.tick_interval = max(0.02, min(float(tick_interval), 5.0))
        except Exception:
            self.tick_interval = 0.1
        self.broadcast_ip = broadcast_ip or _get_broadcast_address()
        self.leader_id = "leader-pi"
        self.is_running = False
        self.start_time = None
        self.sync_sock = None
        # Optional provider that returns the leader's authoritative media time (seconds)
        self.time_provider: Optional[Callable[[], float]] = None
        # Optional provider that returns the leader's media duration (seconds)
        self.duration_provider: Optional[Callable[[], float]] = None

    def setup_socket(self) -> None:
        """Initialize broadcast socket"""
        try:
            self.sync_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sync_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        except Exception as e:
            raise NetworkError(f"Failed to setup sync socket: {e}")

    def start_broadcasting(self, start_time: float) -> None:
        """Start broadcasting time sync"""
        self.start_time = start_time
        self.is_running = True

        if not self.sync_sock:
            self.setup_socket()

        from core.logger import log_info
        log_info(f"Sync: Starting broadcast on {self.broadcast_ip}:{self.sync_port}", component="network")

        def broadcast_loop():
            while self.is_running:
                if self.start_time:
                    try:
                        current_time = None
                        time_source = "wall"
                        
                        if self.time_provider is not None:
                            provided_time = self.time_provider()
                            if provided_time is not None:
                                current_time = float(provided_time)
                                time_source = "media"
                        
                        if current_time is None:
                            current_time = time.time() - self.start_time
                            time_source = "wall"

                        # Include optional duration for diagnostics
                        leader_duration = None
                        if self.duration_provider:
                            try:
                                leader_duration = float(self.duration_provider())
                            except Exception:
                                pass

                        payload = json.dumps(
                            {
                                "type": "sync",
                                "time": current_time,
                                "leader_id": self.leader_id,
                                "source": time_source,
                                "duration": leader_duration,
                                "sent_at": time.time(),
                            }
                        )

                        self.sync_sock.sendto(
                            payload.encode(), (self.broadcast_ip, self.sync_port)
                        )
                    except Exception:
                        pass

                time.sleep(self.tick_interval)

        thread = threading.Thread(target=broadcast_loop, daemon=True)
        thread.start()
        # print("Started time sync broadcasting")

    def set_time_provider(self, provider: Optional[Callable[[], float]]) -> None:
        """Set an optional provider returning the leader's media time in seconds"""
        self.time_provider = provider

    def set_duration_provider(self, provider: Optional[Callable[[], float]]) -> None:
        """Set an optional provider returning the leader's media duration in seconds"""
        self.duration_provider = provider

    def stop_broadcasting(self) -> None:
        """Stop broadcasting time sync"""
        self.is_running = False
        if self.sync_sock:
            try:
                self.sync_sock.close()
            except Exception:
                pass
        # print("Stopped time sync broadcasting")


class SyncReceiver:
    """Handles time sync reception for collaborators"""

    def __init__(self, sync_port: int = 5005, sync_callback: Optional[Callable] = None):
        self.sync_port = sync_port
        self.sync_callback = sync_callback
        self.is_running = False
        self.sync_sock = None
        self.last_sync_time = 0

    def setup_socket(self) -> None:
        """Initialize sync receive socket"""
        try:
            self.sync_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sync_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            
            if hasattr(socket, "SO_REUSEPORT"):
                try:
                    self.sync_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
                except Exception:
                    pass
                    
            self.sync_sock.bind(("", self.sync_port))
        except Exception as e:
            raise NetworkError(f"Failed to setup sync receive socket: {e}")

    def start_listening(self) -> None:
        """Start listening for collaborator messages"""
        self.is_running = True

        if not self.control_sock:
            try:
                self.setup_socket()
            except Exception as e:
                print(f"[ERROR] Failed to setup control socket: {e}")
                return

        def listen_loop():
            while self.is_running:
                try:
                    data, addr = self.control_sock.recvfrom(UDP_MAX_DATAGRAM_SIZE)
                    msg_text = data.decode()
                    # print(f"
[NET] Received from {addr}: {msg_text}")
                    msg = json.loads(msg_text)
                    
                    # Always update registry for any valid message from a device
                    self._update_collaborator_info(msg, addr)

                    msg_type = msg.get("type")
                    if msg_type in self.message_handlers:
                        self.message_handlers[msg_type](msg, addr)
                    elif "__all__" in self.message_handlers:
                        self.message_handlers["__all__"](msg, addr)
                    else:
                        self._handle_default_message(msg, addr)

                except socket.timeout:
                    continue
                except json.JSONDecodeError as e:
                    print(f"[WARN] Net: Received malformed packet from {addr}: {e}")
                except Exception as e:
                    if self.is_running:
                        print(f"[ERROR] Net: Listener loop crash prevented: {e}")
                        import time
                        time.sleep(0.5)

        thread = threading.Thread(target=listen_loop, daemon=True)
        thread.start()
        print(f"[INFO] Command listener active on port {self.control_port}")

