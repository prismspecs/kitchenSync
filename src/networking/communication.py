#!/usr/bin/env python3
"""
Networking Components for kSync
Handles time sync and command communication between leader and collaborators
"""

import json
import socket
import struct
import threading
import time
from typing import Callable, Optional, Dict, Any
from core.logger import log_info, log_warning


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
        # When True, even if time_provider returns a value, label source as "wall".
        # Used when the driver is in fakesink/mock mode so the collaborator doesn't
        # compare wall-clock position against its own hardware-decoded position
        # (which has ~400ms pipeline delay).
        self.is_wall_clock: bool = False

    def setup_socket(self) -> None:
        """Initialize broadcast socket"""
        try:
            self.sync_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sync_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        except Exception as e:
            raise NetworkError(f"Failed to setup sync socket: {e}")

    def set_unicast_targets(self, targets: list[str], use_broadcast: bool = False) -> None:
        """Set unicast addresses to send sync to, one per peer."""
        self._unicast_targets = targets
        self._use_broadcast = use_broadcast

    def start_broadcasting(self, start_time: float) -> None:
        """Start broadcasting time sync"""
        self.start_time = start_time
        self.is_running = True

        if not self.sync_sock:
            self.setup_socket()

        targets = getattr(self, "_unicast_targets", [])
        use_bcast = getattr(self, "_use_broadcast", not bool(targets))
        if targets:
            log_warning(f"Sync: Sending unicast to {targets} on port {self.sync_port}", component="network")
        if use_bcast:
            log_warning(f"Sync: Broadcasting on {self.broadcast_ip}:{self.sync_port}", component="network")

        def broadcast_loop():
            while self.is_running:
                if self.start_time:
                    try:
                        current_time = None
                        time_source = "wall"
                        position_read_time = None
                        
                        if self.time_provider is not None:
                            position_read_time = time.time()
                            provided_time = self.time_provider()
                            if provided_time is not None:
                                current_time = float(provided_time)
                                if not self.is_wall_clock:
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

                        now = time.time()
                        payload = json.dumps(
                            {
                                "type": "sync",
                                "time": current_time,
                                "leader_id": self.leader_id,
                                "source": time_source,
                                "duration": leader_duration,
                                "sent_at": now,
                                "position_read_time": position_read_time or now,
                            }
                        )

                        if use_bcast:
                            self.sync_sock.sendto(
                                payload.encode(), (self.broadcast_ip, self.sync_port)
                            )
                        for target in targets:
                            self.sync_sock.sendto(
                                payload.encode(), (target, self.sync_port)
                            )
                    except Exception as e:
                        # Rate-limited: silence here once hid a dead unicast
                        # target for weeks (sync_peer_ip pointing nowhere).
                        now_err = time.time()
                        if now_err - getattr(self, "_last_send_error_at", 0.0) > 10.0:
                            self._last_send_error_at = now_err
                            log_warning(f"Sync: send failed ({e}) - check network / sync_peer_ip", component="network")

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


def _extract_kernel_timestamp(ancdata) -> Optional[float]:
    """Extract kernel receive timestamp from recvmsg ancillary data if available."""
    for cmsg_level, cmsg_type, cmsg_data in ancdata:
        if cmsg_level == socket.SOL_SOCKET:
            # SO_TIMESTAMPNS (35) - timespec (seconds, nanoseconds)
            if cmsg_type == 35:
                if len(cmsg_data) == 16:
                    sec, nsec = struct.unpack("qq" if struct.calcsize("l") == 8 else "ll", cmsg_data)
                    return sec + nsec / 1e9
            # SO_TIMESTAMP (29) - timeval (seconds, microseconds)
            elif cmsg_type == 29:
                if len(cmsg_data) == 16:
                    sec, usec = struct.unpack("qq" if struct.calcsize("l") == 8 else "ll", cmsg_data)
                    return sec + usec / 1e6
                elif len(cmsg_data) == 8:
                    sec, usec = struct.unpack("ii", cmsg_data)
                    return sec + usec / 1e6
    return None


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
            
            # Enable kernel-level software timestamping on the socket (SO_TIMESTAMPNS or SO_TIMESTAMP)
            for opt in ["SO_TIMESTAMPNS", "SO_TIMESTAMP"]:
                if hasattr(socket, opt):
                    try:
                        self.sync_sock.setsockopt(socket.SOL_SOCKET, getattr(socket, opt), 1)
                        break
                    except Exception:
                        pass
                    
            self.sync_sock.bind(("", self.sync_port))
        except Exception as e:
            raise NetworkError(f"Failed to setup sync receive socket: {e}")

    def start_listening(self) -> None:
        """Start listening for time sync"""
        self.is_running = True

        if not self.sync_sock:
            self.setup_socket()

        def listen_loop():
            # Set a high buffer size for the socket to avoid OS-level drops
            try:
                self.sync_sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1024 * 128)
            except Exception:
                pass

            # Use a shorter timeout for responsive shutdown
            self.sync_sock.settimeout(0.5)
            
            while self.is_running:
                try:
                    # 1. Block on the first packet (lowest CPU)
                    try:
                        if hasattr(self.sync_sock, "recvmsg"):
                            data, ancdata, flags, addr = self.sync_sock.recvmsg(1024, 128)
                            received_at = _extract_kernel_timestamp(ancdata) or time.time()
                        else:
                            data, addr = self.sync_sock.recvfrom(1024)
                            received_at = time.time()
                    except socket.timeout:
                        continue
                    except (socket.error, OSError):
                        if not self.is_running:
                            break
                        continue
                    
                    # 2. Aggressively drain the buffer to find the NEWEST packet
                    # This eliminates 'buffer bloat' latency.
                    self.sync_sock.setblocking(False)
                    packets_drained = 0
                    while self.is_running:
                        try:
                            if hasattr(self.sync_sock, "recvmsg"):
                                new_data, new_ancdata, new_flags, new_addr = self.sync_sock.recvmsg(1024, 128)
                                data, addr = new_data, new_addr
                                received_at = _extract_kernel_timestamp(new_ancdata) or time.time()
                            else:
                                new_data, new_addr = self.sync_sock.recvfrom(1024)
                                data, addr = new_data, new_addr
                                received_at = time.time()
                            packets_drained += 1
                        except (socket.error, BlockingIOError):
                            break
                    
                    if not self.is_running:
                        break
                        
                    # Restore blocking mode with timeout
                    self.sync_sock.setblocking(True)
                    self.sync_sock.settimeout(0.5)

                    msg = json.loads(data.decode())

                    if msg.get("type") == "sync":
                        self.last_sync_time = received_at
                        leader_time = msg.get("time", 0)
                        leader_id = msg.get("leader_id", "unknown")
                        sent_at = msg.get("sent_at")
                        position_read_time = msg.get("position_read_time", sent_at)

                        if self.sync_callback:
                            try:
                                # Execute callback with high precision timestamp and leader IP
                                source = msg.get("source", "wall")
                                leader_ip = addr[0] if addr else None
                                try:
                                    self.sync_callback(leader_time, received_at, leader_id, sent_at, source, position_read_time, leader_ip)
                                except TypeError:
                                    try:
                                        self.sync_callback(leader_time, received_at, leader_id, sent_at, source, position_read_time)
                                    except TypeError:
                                        self.sync_callback(leader_time, received_at, leader_id)
                                        
                                if packets_drained > 5:
                                    log_info(
                                        f"Sync: Drained {packets_drained} stale packets (Critical latency recovered)",
                                        component="sync",
                                    )

                            except Exception:
                                pass # Avoid stopping loop on user callback error

                except json.JSONDecodeError:
                    continue
                except Exception:
                    if self.is_running:
                        pass

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

    def __init__(self, control_port: int = 5006, broadcast_ip: Optional[str] = None, debug_mode: bool = False):
        self.control_port = control_port
        self.broadcast_ip = broadcast_ip or _get_broadcast_address()
        self.control_sock = None
        self.is_running = False
        self.collaborators = {}
        self.message_handlers = {}
        self.debug_mode = debug_mode
        
        # Latency tracking
        self._rtt_samples = {} # Dict[device_id, list]
        self._ping_sent_at = {} # Dict[device_id, float]
        self._latency_probe_thread = None

    def get_average_rtt(self) -> float:
        """Calculate the average round-trip time across all collaborators."""
        all_samples = []
        for samples in self._rtt_samples.values():
            all_samples.extend(samples)
        if not all_samples:
            return 0.0
        return sum(all_samples) / len(all_samples)

    def get_device_average_rtt(self, device_id: str) -> float:
        """Return the average RTT for a specific collaborator."""
        samples = self._rtt_samples.get(device_id, [])
        if not samples:
            return 0.0
        return sum(samples) / len(samples)

    def get_device_last_rtt(self, device_id: str) -> float:
        """Return the most recent RTT for a specific collaborator."""
        samples = self._rtt_samples.get(device_id, [])
        if not samples:
            return 0.0
        return samples[-1]

    def _record_rtt_sample(self, device_id: str, rtt: float) -> None:
        """Store a bounded RTT sample for a collaborator."""
        if rtt < 0.0 or rtt > 2.0:
            return
        if device_id not in self._rtt_samples:
            self._rtt_samples[device_id] = []
        self._rtt_samples[device_id].append(rtt)
        if len(self._rtt_samples[device_id]) > 10:
            self._rtt_samples[device_id].pop(0)

    def setup_socket(self) -> None:
        """Initialize command socket"""
        try:
            self.control_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.control_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.control_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            
            # Use SO_REUSEPORT if available (Linux/macOS) to allow multiple 
            # listeners on the same machine to share the port.
            if hasattr(socket, "SO_REUSEPORT"):
                try:
                    self.control_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
                except Exception:
                    pass # Ignore if OS doesn't support it in practice
                    
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
                    data, addr = self.control_sock.recvfrom(UDP_MAX_DATAGRAM_SIZE)
                    msg_text = data.decode()
                    # Per-datagram at INFO: silent unless enable_system_logging
                    # (was a print() — journal noise scaling with node count)
                    log_info(f"Net: received from {addr}: {msg_text[:300]}", component="network")
                    msg = json.loads(msg_text)
                    
                    msg_type = msg.get("type")
                    if msg_type in self.message_handlers:
                        self.message_handlers[msg_type](msg, addr)
                    elif "__all__" in self.message_handlers:
                        self.message_handlers["__all__"](msg, addr)
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

    def start_latency_probing(self, interval: float = 2.0) -> None:
        """Periodically measure collaborator RTT using explicit ping/pong messages."""
        if self._latency_probe_thread and self._latency_probe_thread.is_alive():
            return

        def probe_loop():
            while self.is_running:
                try:
                    self.send_ping()
                except Exception:
                    pass
                time.sleep(interval)

        self._latency_probe_thread = threading.Thread(target=probe_loop, daemon=True)
        self._latency_probe_thread.start()

    def _ensure_send_socket(self) -> None:
        """Ensure a socket is available for sending commands."""
        if self.control_sock is None:
            self.control_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.control_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

    def send_command(
        self, command: Dict[str, Any], target_pi: Optional[str] = None
    ) -> None:
        """Send command to collaborator Pi(s)"""
        self._ensure_send_socket()
        payload = json.dumps(command)

        # 1. Direct Send (to specific target or ALL registered collaborators)
        if target_pi:
            if target_pi in self.collaborators:
                ip = self.collaborators[target_pi]["ip"]
                try:
                    self._ping_sent_at[target_pi] = time.time()
                    self.control_sock.sendto(payload.encode(), (ip, self.control_port))
                    log_info(f"Net: sent {command['type']} directly to {target_pi} ({ip})", component="network")
                except Exception:
                    pass
        else:
            # Send to every registered IP directly for maximum reliability
            for device_id, info in self.collaborators.items():
                try:
                    self._ping_sent_at[device_id] = time.time()
                    self.control_sock.sendto(payload.encode(), (info["ip"], self.control_port))
                    log_info(f"Net: sent {command['type']} directly to {device_id} ({info['ip']})", component="network")
                except Exception:
                    pass

        # 2. Broadcast (as fallback and for unregistered nodes)
        try:
            self.control_sock.sendto(
                payload.encode(), (self.broadcast_ip, self.control_port)
            )
            log_info(f"Net: broadcast {command['type']} to {self.broadcast_ip}", component="network")
        except Exception as e:
            log_warning(f"Broadcast failed for {command['type']}: {e}", component="network")

    def send_ping(self, target_pi: Optional[str] = None) -> None:
        """Send an explicit latency probe to one or all registered collaborators."""
        self._ensure_send_socket()
        ping = {"type": "ping", "sent_at": time.time()}
        targets = []

        if target_pi:
            info = self.collaborators.get(target_pi)
            if info:
                targets.append((target_pi, info["ip"]))
        else:
            targets = [
                (device_id, info["ip"])
                for device_id, info in self.collaborators.items()
                if info.get("online", True)
            ]

        for device_id, ip in targets:
            try:
                self._ping_sent_at[device_id] = time.monotonic()
                self.control_sock.sendto(json.dumps(ping).encode(), (ip, self.control_port))
            except Exception:
                self._ping_sent_at.pop(device_id, None)

    def _handle_default_message(self, msg: Dict[str, Any], addr: tuple) -> None:
        """Handle default message types"""
        msg_type = msg.get("type")
        device_id = msg.get("device_id")
        if not device_id:
            return

        if msg_type == "pong":
            sent_at = self._ping_sent_at.pop(device_id, None)
            if sent_at is not None:
                rtt = time.monotonic() - sent_at
                self._record_rtt_sample(device_id, rtt)
                # Send the RTT / 2 back to the collaborator so they know their transport latency!
                latency_msg = {
                    "type": "latency_update",
                    "latency": rtt / 2.0
                }
                self.send_command(latency_msg, target_pi=device_id)
            return

        # If a new ID appears from an IP that we already know, 
        # it's likely a device that restarted and changed its ID.
        # Prune the old ID from that IP to avoid duplicate 'start' commands.
        for old_id, info in list(self.collaborators.items()):
            if info["ip"] == addr[0] and old_id != device_id:
                log_info(f"Net: Device at {addr[0]} changed ID from {old_id} to {device_id}. Pruning old entry.", component="network")
                del self.collaborators[old_id]

        if msg_type == "register":
            self.collaborators[device_id] = {
                "ip": addr[0],
                "last_seen": time.time(),
                "status": msg.get("status", "unknown"),
                "video_file": msg.get("video_file", ""),
                "video_driver": msg.get("video_driver", ""),
                "is_optimized": msg.get("is_optimized", False),
                "hard_seeks": msg.get("hard_seeks", 0),
            }

        elif msg_type == "heartbeat":
            self.collaborators[device_id] = {
                "ip": addr[0],
                "last_seen": time.time(),
                "status": msg.get("status", "ready"),
                "video_file": msg.get(
                    "video_file",
                    self.collaborators.get(device_id, {}).get("video_file", ""),
                ),
                "video_driver": msg.get(
                    "video_driver",
                    self.collaborators.get(device_id, {}).get("video_driver", ""),
                ),
                "is_optimized": msg.get("is_optimized", False),
                "hard_seeks": msg.get("hard_seeks", 0),
                "sync_deviation": msg.get("sync_deviation", 0.0),
                "playback_rate": msg.get("playback_rate", 1.0),
            }

    def get_collaborators(self) -> Dict[str, Dict]:
        """Get current collaborator status and prune long-dead ones"""
        current_time = time.time()
        for device_id, info in list(self.collaborators.items()):
            last_seen = current_time - info["last_seen"]
            info["online"] = last_seen < 15
            
            # Prune if gone for more than 5 minutes
            if last_seen > 300:
                del self.collaborators[device_id]
                
        return self.collaborators


class CommandListener:
    """Handles command listening for collaborators"""

    def __init__(self, control_port: int = 5006):
        self.control_port = control_port
        self.control_sock = None
        self.is_running = False
        self.message_handlers = {}
        # Cached send socket + broadcast address (see send_message)
        self._send_sock = None
        self._broadcast_ip = None

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
                    data, addr = self.control_sock.recvfrom(UDP_MAX_DATAGRAM_SIZE)
                    msg = json.loads(data.decode())
                    
                    msg_type = msg.get("type")
                    if msg_type in self.message_handlers:
                        self.message_handlers[msg_type](msg, addr)
                    elif "__all__" in self.message_handlers:
                        self.message_handlers["__all__"](msg, addr)

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

    def register_callback(self, callback: Callable) -> None:
        """Register a catch-all callback for any message"""
        self.message_handlers["__all__"] = callback

    def send_registration(self, device_id: str, video_file: str, hard_seeks: int = 0) -> None:
        """Send registration to leader"""
        registration = {
            "type": "register",
            "device_id": device_id,
            "status": "ready",
            "video_file": video_file,
            "hard_seeks": hard_seeks,
        }

        self.send_message(registration)

    def send_message(self, message: Dict[str, Any], host: Optional[str] = None) -> None:
        """Send a control message directly or via broadcast.

        Socket and broadcast address are cached: this runs for every 2s
        heartbeat, and the old per-call socket + 8.8.8.8-probe pattern
        created two sockets per message for nothing. On any send failure the
        cache resets so a changed network (DHCP renew, interface flap) is
        picked up on the next attempt.
        """
        try:
            if self._send_sock is None:
                self._send_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                self._send_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            if host is None:
                if self._broadcast_ip is None:
                    self._broadcast_ip = _get_broadcast_address()
                destination_host = self._broadcast_ip
            else:
                destination_host = host
            self._send_sock.sendto(
                json.dumps(message).encode(),
                (destination_host, self.control_port),
            )
        except Exception:
            try:
                if self._send_sock:
                    self._send_sock.close()
            except Exception:
                pass
            self._send_sock = None
            self._broadcast_ip = None

    def send_heartbeat(self, device_id: str, status: str = "ready", hard_seeks: int = 0, video_file: str = "", is_optimized: bool = False, video_driver: str = "", sync_deviation: float = 0.0, playback_rate: float = 1.0) -> None:
        """Send heartbeat to leader"""
        heartbeat = {
            "type": "heartbeat",
            "device_id": device_id,
            "status": status,
            "hard_seeks": hard_seeks,
            "video_file": video_file,
            "is_optimized": is_optimized,
            "video_driver": video_driver,
            "sync_deviation": sync_deviation,
            "playback_rate": playback_rate,
        }
        self.send_message(heartbeat)
