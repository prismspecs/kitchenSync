#!/usr/bin/env python3
"""
Networking Components for KitchenSync
Handles time sync and command communication between leader and collaborators
"""

import json
import socket
import threading
import time
from typing import Callable, Optional, Dict, Any


class NetworkError(Exception):
    """Raised when network operations fail"""

    pass


class SyncBroadcaster:
    """Handles time sync broadcasting for leader"""

    def __init__(self, sync_port: int = 5005, tick_interval: float = 0.1):
        self.sync_port = sync_port
        # Clamp to a safe range to avoid CPU burn or sluggish updates
        try:
            self.tick_interval = max(0.02, min(float(tick_interval), 5.0))
        except Exception:
            self.tick_interval = 0.1
        self.broadcast_ip = "255.255.255.255"
        self.leader_id = "leader-001"
        self.is_running = False
        self.start_time = None
        self.sync_sock = None

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

        def broadcast_loop():
            while self.is_running:
                if self.start_time:
                    current_time = time.time() - self.start_time
                    payload = json.dumps(
                        {
                            "type": "sync",
                            "time": current_time,
                            "leader_id": self.leader_id,
                        }
                    )

                    try:
                        self.sync_sock.sendto(
                            payload.encode(), (self.broadcast_ip, self.sync_port)
                        )
                    except Exception as e:
                        pass  # Ignore broadcast errors

                time.sleep(self.tick_interval)

        thread = threading.Thread(target=broadcast_loop, daemon=True)
        thread.start()
        # print("Started time sync broadcasting")

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
            self.sync_sock.bind(("", self.sync_port))
        except Exception as e:
            raise NetworkError(f"Failed to setup sync receive socket: {e}")

    def start_listening(self) -> None:
        """Start listening for time sync"""
        self.is_running = True

        if not self.sync_sock:
            self.setup_socket()

        def listen_loop():
            while self.is_running:
                try:
                    data, addr = self.sync_sock.recvfrom(1024)
                    msg = json.loads(data.decode())

                    if msg.get("type") == "sync":
                        self.last_sync_time = time.time()
                        leader_time = msg.get("time", 0)

                        if self.sync_callback:
                            self.sync_callback(leader_time)

                except json.JSONDecodeError:
                    continue
                except Exception as e:
                    if self.is_running:
                        pass  # Ignore sync listener errors

        thread = threading.Thread(target=listen_loop, daemon=True)
        thread.start()
        # print("Started listening for time sync")

    def stop_listening(self) -> None:
        """Stop listening for time sync"""
        self.is_running = False
        if self.sync_sock:
            try:
                self.sync_sock.close()
            except Exception:
                pass
        # print("Stopped sync listening")

    def is_sync_active(self, timeout: float = 5.0) -> bool:
        """Check if sync is still active"""
        return time.time() - self.last_sync_time < timeout


class CommandManager:
    """Handles command communication for leader"""

    def __init__(self, control_port: int = 5006):
        self.control_port = control_port
        self.broadcast_ip = "255.255.255.255"
        self.control_sock = None
        self.is_running = False
        self.collaborators = {}
        self.message_handlers = {}

    def setup_socket(self) -> None:
        """Initialize command socket"""
        try:
            self.control_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.control_sock.bind(("", self.control_port))
            self.control_sock.settimeout(1.0)
        except Exception as e:
            raise NetworkError(f"Failed to setup command socket: {e}")

    def start_listening(self) -> None:
        """Start listening for collaborator messages"""
        self.is_running = True

        if not self.control_sock:
            self.setup_socket()

        def listen_loop():
            while self.is_running:
                try:
                    data, addr = self.control_sock.recvfrom(1024)
                    msg = json.loads(data.decode())

                    msg_type = msg.get("type")
                    if msg_type in self.message_handlers:
                        self.message_handlers[msg_type](msg, addr)
                    else:
                        self._handle_default_message(msg, addr)

                except socket.timeout:
                    continue
                except json.JSONDecodeError:
                    continue
                except Exception as e:
                    if self.is_running:
                        pass  # Ignore command listener errors

        thread = threading.Thread(target=listen_loop, daemon=True)
        thread.start()
        # print("Started listening for collaborator commands")

    def stop_listening(self) -> None:
        """Stop listening for commands"""
        self.is_running = False
        if self.control_sock:
            try:
                self.control_sock.close()
            except Exception:
                pass

    def register_handler(self, message_type: str, handler: Callable) -> None:
        """Register a message handler"""
        self.message_handlers[message_type] = handler

    def send_command(
        self, command: Dict[str, Any], target_pi: Optional[str] = None
    ) -> None:
        """Send command to collaborator Pi(s)"""
        payload = json.dumps(command)

        if target_pi and target_pi in self.collaborators:
            # Send to specific Pi
            ip = self.collaborators[target_pi]["ip"]
            try:
                self.control_sock.sendto(payload.encode(), (ip, self.control_port))
                # print(f"Sent command to {target_pi}: {command['type']}")
            except Exception as e:
                pass  # Ignore command send errors
        else:
            # Broadcast to all Pis
            try:
                self.control_sock.sendto(
                    payload.encode(), (self.broadcast_ip, self.control_port)
                )
                # print(f"Broadcast command: {command['type']}")
            except Exception as e:
                pass  # Ignore broadcast errors

    def _handle_default_message(self, msg: Dict[str, Any], addr: tuple) -> None:
        """Handle default message types"""
        msg_type = msg.get("type")

        if msg_type == "register":
            device_id = msg.get("device_id")
            if device_id:
                self.collaborators[device_id] = {
                    "ip": addr[0],
                    "last_seen": time.time(),
                    "status": msg.get("status", "unknown"),
                }
                # print(f"Registered Pi: {device_id} at {addr[0]}")

        elif msg_type == "heartbeat":
            device_id = msg.get("device_id")
            if device_id in self.collaborators:
                self.collaborators[device_id]["last_seen"] = time.time()

    def get_collaborators(self) -> Dict[str, Dict]:
        """Get current collaborator status"""
        current_time = time.time()
        for device_id, info in self.collaborators.items():
            last_seen = current_time - info["last_seen"]
            info["online"] = last_seen < 5
        return self.collaborators


class CommandListener:
    """Handles command listening for collaborators"""

    def __init__(self, control_port: int = 5006):
        self.control_port = control_port
        self.control_sock = None
        self.is_running = False
        self.message_handlers = {}

    def setup_socket(self) -> None:
        """Initialize command socket"""
        try:
            self.control_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.control_sock.bind(("", self.control_port))
        except Exception as e:
            raise NetworkError(f"Failed to setup command socket: {e}")

    def start_listening(self) -> None:
        """Start listening for commands"""
        self.is_running = True

        if not self.control_sock:
            self.setup_socket()

        def listen_loop():
            while self.is_running:
                try:
                    data, addr = self.control_sock.recvfrom(1024)
                    msg = json.loads(data.decode())

                    msg_type = msg.get("type")
                    if msg_type in self.message_handlers:
                        self.message_handlers[msg_type](msg, addr)

                except json.JSONDecodeError:
                    continue
                except Exception as e:
                    if self.is_running:
                        pass  # Ignore command listener errors

        thread = threading.Thread(target=listen_loop, daemon=True)
        thread.start()
        # print("Started listening for leader commands")

    def stop_listening(self) -> None:
        """Stop listening for commands"""
        self.is_running = False
        if self.control_sock:
            try:
                self.control_sock.close()
            except Exception:
                pass

    def register_handler(self, message_type: str, handler: Callable) -> None:
        """Register a message handler"""
        self.message_handlers[message_type] = handler

    def send_registration(self, device_id: str, video_file: str) -> None:
        """Send registration to leader"""
        registration = {
            "type": "register",
            "device_id": device_id,
            "status": "ready",
            "video_file": video_file,
        }

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.sendto(
                json.dumps(registration).encode(),
                ("255.255.255.255", self.control_port),
            )
            sock.close()
            # print(f"Registered with leader as '{device_id}'")
        except Exception as e:
            pass  # Ignore registration errors

    def send_heartbeat(self, device_id: str, status: str = "ready") -> None:
        """Send heartbeat to leader"""
        heartbeat = {"type": "heartbeat", "device_id": device_id, "status": status}

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.sendto(
                json.dumps(heartbeat).encode(), ("255.255.255.255", self.control_port)
            )
            sock.close()
        except Exception as e:
            pass  # Ignore heartbeat errors
