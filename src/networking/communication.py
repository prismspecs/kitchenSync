#!/usr/bin/env python3
"""
Networking Components for KitchenSync
Handles time sync and command communication between leader and collaborators

This is the preferred networking implementation with improved error handling,
resource management, and thread safety.
"""

import json
import socket
import threading
import time
from typing import Callable, Optional, Dict, Any
from contextlib import contextmanager


class NetworkError(Exception):
    """Raised when network operations fail"""
    pass


@contextmanager
def temp_socket(broadcast: bool = False):
    """Context manager for temporary socket creation"""
    sock = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        if broadcast:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        yield sock
    except Exception as e:
        raise NetworkError(f"Socket operation failed: {e}")
    finally:
        if sock:
            try:
                sock.close()
            except Exception:
                pass


class SyncBroadcaster:
    """Handles time sync broadcasting for leader with improved reliability"""
    
    def __init__(self, sync_port: int = 5005, tick_interval: float = 0.1):
        self.sync_port = sync_port
        self.tick_interval = tick_interval
        self.broadcast_ip = '255.255.255.255'
        self.leader_id = 'leader-001'
        self.is_running = False
        self.start_time = None
        self.sync_sock = None
        self._broadcast_thread = None
        self._lock = threading.Lock()
        
    def setup_socket(self) -> None:
        """Initialize broadcast socket with proper error handling"""
        with self._lock:
            if self.sync_sock:
                return
            try:
                self.sync_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                self.sync_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            except Exception as e:
                raise NetworkError(f"Failed to setup sync socket: {e}")
    
    def start_broadcasting(self, start_time: float) -> None:
        """Start broadcasting time sync"""
        if self.is_running:
            return
            
        self.start_time = start_time
        self.is_running = True
        
        self.setup_socket()
        
        def broadcast_loop():
            while self.is_running:
                try:
                    if self.start_time and self.sync_sock:
                        current_time = time.time() - self.start_time
                        payload = json.dumps({
                            'type': 'sync',
                            'time': current_time,
                            'leader_id': self.leader_id,
                            'timestamp': time.time()
                        })
                        
                        self.sync_sock.sendto(payload.encode('utf-8'), (self.broadcast_ip, self.sync_port))
                except Exception as e:
                    if self.is_running:  # Only log if we should be running
                        print(f"❌ Error broadcasting sync: {e}")
                
                time.sleep(self.tick_interval)
        
        self._broadcast_thread = threading.Thread(target=broadcast_loop, daemon=True)
        self._broadcast_thread.start()
        print("🔄 Started time sync broadcasting")
    
    def stop_broadcasting(self) -> None:
        """Stop broadcasting time sync"""
        self.is_running = False
        
        # Wait for thread to finish
        if self._broadcast_thread and self._broadcast_thread.is_alive():
            self._broadcast_thread.join(timeout=2.0)
        
        # Clean up socket
        with self._lock:
            if self.sync_sock:
                try:
                    self.sync_sock.close()
                    self.sync_sock = None
                except Exception:
                    pass
        print("🛑 Stopped time sync broadcasting")


class SyncReceiver:
    """Handles time sync reception for collaborators with improved reliability"""
    
    def __init__(self, sync_port: int = 5005, sync_callback: Optional[Callable] = None):
        self.sync_port = sync_port
        self.sync_callback = sync_callback
        self.is_running = False
        self.sync_sock = None
        self.last_sync_time = 0
        self._listen_thread = None
        self._lock = threading.Lock()
        
    def setup_socket(self) -> None:
        """Initialize sync receive socket"""
        with self._lock:
            if self.sync_sock:
                return
            try:
                self.sync_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                self.sync_sock.bind(('', self.sync_port))
                self.sync_sock.settimeout(1.0)
            except Exception as e:
                raise NetworkError(f"Failed to setup sync receive socket: {e}")
    
    def start_listening(self) -> None:
        """Start listening for time sync"""
        if self.is_running:
            return
            
        self.is_running = True
        self.setup_socket()
        
        def listen_loop():
            while self.is_running:
                try:
                    if not self.sync_sock:
                        break
                        
                    data, addr = self.sync_sock.recvfrom(1024)
                    msg = json.loads(data.decode('utf-8'))
                    
                    if msg.get('type') == 'sync':
                        self.last_sync_time = time.time()
                        leader_time = msg.get('time', 0)
                        
                        if self.sync_callback:
                            self.sync_callback(leader_time)
                            
                except socket.timeout:
                    continue
                except json.JSONDecodeError:
                    continue
                except Exception as e:
                    if self.is_running:
                        print(f"❌ Error in sync listener: {e}")
        
        self._listen_thread = threading.Thread(target=listen_loop, daemon=True)
        self._listen_thread.start()
        print("👂 Started listening for time sync")
    
    def stop_listening(self) -> None:
        """Stop listening for time sync"""
        self.is_running = False
        
        # Wait for thread to finish
        if self._listen_thread and self._listen_thread.is_alive():
            self._listen_thread.join(timeout=2.0)
        
        # Clean up socket
        with self._lock:
            if self.sync_sock:
                try:
                    self.sync_sock.close()
                    self.sync_sock = None
                except Exception:
                    pass
        print("🛑 Stopped sync listening")
    
    def is_sync_active(self, timeout: float = 5.0) -> bool:
        """Check if sync is still active"""
        return time.time() - self.last_sync_time < timeout


class CommandManager:
    """Handles command communication for leader with improved reliability"""
    
    def __init__(self, control_port: int = 5006):
        self.control_port = control_port
        self.broadcast_ip = '255.255.255.255'
        self.control_sock = None
        self.is_running = False
        self.collaborators = {}
        self.message_handlers = {}
        self._listen_thread = None
        self._lock = threading.Lock()
        
    def setup_socket(self) -> None:
        """Initialize command socket"""
        with self._lock:
            if self.control_sock:
                return
            try:
                self.control_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                self.control_sock.bind(('', self.control_port))
                self.control_sock.settimeout(1.0)
            except Exception as e:
                raise NetworkError(f"Failed to setup command socket: {e}")
    
    def start_listening(self) -> None:
        """Start listening for collaborator messages"""
        if self.is_running:
            return
            
        self.is_running = True
        self.setup_socket()
        
        def listen_loop():
            while self.is_running:
                try:
                    if not self.control_sock:
                        break
                        
                    data, addr = self.control_sock.recvfrom(1024)
                    msg = json.loads(data.decode('utf-8'))
                    
                    msg_type = msg.get('type')
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
                        print(f"❌ Error in command listener: {e}")
        
        self._listen_thread = threading.Thread(target=listen_loop, daemon=True)
        self._listen_thread.start()
        print("👂 Started listening for collaborator commands")
    
    def stop_listening(self) -> None:
        """Stop listening for commands"""
        self.is_running = False
        
        # Wait for thread to finish
        if self._listen_thread and self._listen_thread.is_alive():
            self._listen_thread.join(timeout=2.0)
        
        # Clean up socket
        with self._lock:
            if self.control_sock:
                try:
                    self.control_sock.close()
                    self.control_sock = None
                except Exception:
                    pass
        print("🛑 Stopped command listening")
    
    def register_handler(self, message_type: str, handler: Callable) -> None:
        """Register a message handler"""
        self.message_handlers[message_type] = handler
    
    def send_command(self, command: Dict[str, Any], target_pi: Optional[str] = None) -> None:
        """Send command to collaborator Pi(s)"""
        # Add timestamp to command
        command = command.copy()
        command['timestamp'] = time.time()
        payload = json.dumps(command)
        
        try:
            if target_pi and target_pi in self.collaborators:
                # Send to specific Pi
                ip = self.collaborators[target_pi]['ip']
                if not self.control_sock:
                    raise NetworkError("Control socket not initialized")
                self.control_sock.sendto(payload.encode('utf-8'), (ip, self.control_port))
                print(f"📤 Sent command to {target_pi}: {command['type']}")
            else:
                # Broadcast to all Pis
                if not self.control_sock:
                    raise NetworkError("Control socket not initialized")
                self.control_sock.sendto(payload.encode('utf-8'), (self.broadcast_ip, self.control_port))
                print(f"📡 Broadcast command: {command['type']}")
        except Exception as e:
            raise NetworkError(f"Failed to send command: {e}")
    
    def _handle_default_message(self, msg: Dict[str, Any], addr: tuple) -> None:
        """Handle default message types"""
        msg_type = msg.get('type')
        
        if msg_type == 'register':
            pi_id = msg.get('pi_id')
            if pi_id:
                with self._lock:
                    self.collaborators[pi_id] = {
                        'ip': addr[0],
                        'last_seen': time.time(),
                        'status': msg.get('status', 'unknown'),
                        'video_file': msg.get('video_file', ''),
                        'registered_at': time.time()
                    }
                print(f"✅ Registered Pi: {pi_id} at {addr[0]}")
                
        elif msg_type == 'heartbeat':
            pi_id = msg.get('pi_id')
            if pi_id and pi_id in self.collaborators:
                with self._lock:
                    self.collaborators[pi_id]['last_seen'] = time.time()
                    self.collaborators[pi_id]['status'] = msg.get('status', 'ready')
    
    def get_collaborators(self) -> Dict[str, Dict]:
        """Get current collaborator status"""
        current_time = time.time()
        result = {}
        
        with self._lock:
            for pi_id, info in self.collaborators.items():
                info_copy = info.copy()
                last_seen = current_time - info['last_seen']
                info_copy['online'] = last_seen < 5
                info_copy['last_seen_seconds'] = last_seen
                result[pi_id] = info_copy
        
        return result


class CommandListener:
    """Handles command listening for collaborators with improved reliability"""
    
    def __init__(self, control_port: int = 5006):
        self.control_port = control_port
        self.control_sock = None
        self.is_running = False
        self.message_handlers = {}
        self._listen_thread = None
        self._lock = threading.Lock()
        self._last_heartbeat = 0
        
    def setup_socket(self) -> None:
        """Initialize command socket"""
        with self._lock:
            if self.control_sock:
                return
            try:
                self.control_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                self.control_sock.bind(('', self.control_port))
                self.control_sock.settimeout(1.0)
            except Exception as e:
                raise NetworkError(f"Failed to setup command socket: {e}")
    
    def start_listening(self) -> None:
        """Start listening for commands"""
        if self.is_running:
            return
            
        self.is_running = True
        self.setup_socket()
        
        def listen_loop():
            while self.is_running:
                try:
                    if not self.control_sock:
                        break
                        
                    data, addr = self.control_sock.recvfrom(1024)
                    msg = json.loads(data.decode('utf-8'))
                    
                    msg_type = msg.get('type')
                    if msg_type in self.message_handlers:
                        self.message_handlers[msg_type](msg, addr)
                        
                except socket.timeout:
                    continue
                except json.JSONDecodeError:
                    continue
                except Exception as e:
                    if self.is_running:
                        print(f"❌ Error in command listener: {e}")
        
        self._listen_thread = threading.Thread(target=listen_loop, daemon=True)
        self._listen_thread.start()
        print("👂 Started listening for leader commands")
    
    def stop_listening(self) -> None:
        """Stop listening for commands"""
        self.is_running = False
        
        # Wait for thread to finish
        if self._listen_thread and self._listen_thread.is_alive():
            self._listen_thread.join(timeout=2.0)
        
        # Clean up socket
        with self._lock:
            if self.control_sock:
                try:
                    self.control_sock.close()
                    self.control_sock = None
                except Exception:
                    pass
        print("🛑 Stopped command listening")
    
    def register_handler(self, message_type: str, handler: Callable) -> None:
        """Register a message handler"""
        self.message_handlers[message_type] = handler
    
    def send_registration(self, pi_id: str, video_file: str, status: str = 'ready') -> None:
        """Send registration to leader"""
        registration = {
            'type': 'register',
            'pi_id': pi_id,
            'status': status,
            'video_file': video_file,
            'timestamp': time.time()
        }
        
        try:
            with temp_socket(broadcast=True) as sock:
                sock.sendto(json.dumps(registration).encode('utf-8'), ('255.255.255.255', self.control_port))
            print(f"📤 Registered with leader as '{pi_id}'")
        except Exception as e:
            raise NetworkError(f"Failed to register with leader: {e}")
    
    def send_heartbeat(self, pi_id: str, status: str = 'ready') -> None:
        """Send heartbeat to leader with rate limiting"""
        current_time = time.time()
        
        # Rate limit heartbeats to prevent spam
        if current_time - self._last_heartbeat < 1.0:
            return
        
        heartbeat = {
            'type': 'heartbeat',
            'pi_id': pi_id,
            'status': status,
            'timestamp': current_time
        }
        
        try:
            with temp_socket(broadcast=True) as sock:
                sock.sendto(json.dumps(heartbeat).encode('utf-8'), ('255.255.255.255', self.control_port))
            self._last_heartbeat = current_time
        except Exception as e:
            print(f"⚠️ Error sending heartbeat: {e}")
    
    def send_status_update(self, pi_id: str, status: str, additional_data: Dict[str, Any] = None) -> None:
        """Send a status update to the leader"""
        status_msg = {
            'type': 'status_update',
            'pi_id': pi_id,
            'status': status,
            'timestamp': time.time()
        }
        
        if additional_data:
            status_msg.update(additional_data)
        
        try:
            with temp_socket(broadcast=True) as sock:
                sock.sendto(json.dumps(status_msg).encode('utf-8'), ('255.255.255.255', self.control_port))
        except Exception as e:
            print(f"⚠️ Failed to send status update: {e}")
