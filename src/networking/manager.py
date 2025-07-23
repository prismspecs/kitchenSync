#!/usr/bin/env python3
"""
Networking components for KitchenSync
Handles UDP communication between leader and collaborators
"""

import json
import socket
import threading
import time
from typing import Optional, Dict, Any, Callable
from contextlib import contextmanager


class NetworkError(Exception):
    """Custom exception for network-related errors"""
    pass


class NetworkManager:
    """Base networking functionality with improved error handling and resource management"""
    
    def __init__(self, sync_port: int = 5005, control_port: int = 5006):
        self.BROADCAST_IP = '255.255.255.255'
        self.SYNC_PORT = sync_port
        self.CONTROL_PORT = control_port
        self.sync_sock = None
        self.control_sock = None
        self._lock = threading.Lock()
    
    def setup_sockets(self) -> None:
        """Initialize UDP sockets - to be implemented by subclasses"""
        raise NotImplementedError("Subclasses must implement setup_sockets")
    
    @contextmanager
    def _temp_socket(self, socket_type: str = 'broadcast'):
        """Context manager for temporary socket creation"""
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            if socket_type == 'broadcast':
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            yield sock
        except Exception as e:
            raise NetworkError(f"Socket operation failed: {e}")
        finally:
            if sock:
                try:
                    sock.close()
                except Exception:
                    pass  # Ignore cleanup errors
    
    def cleanup(self) -> None:
        """Clean up sockets safely"""
        with self._lock:
            for sock_name in ['sync_sock', 'control_sock']:
                sock = getattr(self, sock_name, None)
                if sock:
                    try:
                        sock.close()
                        setattr(self, sock_name, None)
                    except Exception:
                        pass  # Ignore cleanup errors


class LeaderNetworking(NetworkManager):
    """Networking for leader Pi - broadcasts sync and manages collaborators"""
    
    def __init__(self, sync_port: int = 5005, control_port: int = 5006):
        super().__init__(sync_port, control_port)
        self.collaborator_pis = {}
        self.is_running = False
        self.message_handlers = {}
        self._listener_thread = None
    
    def setup_sockets(self) -> None:
        """Setup leader sockets for broadcasting and receiving"""
        with self._lock:
            try:
                # Sync socket for broadcasting
                if not self.sync_sock:
                    self.sync_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    self.sync_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                
                # Control socket for receiving from collaborators
                if not self.control_sock:
                    self.control_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    self.control_sock.bind(('', self.CONTROL_PORT))
                    self.control_sock.settimeout(1.0)
                
            except Exception as e:
                raise NetworkError(f"Failed to setup leader sockets: {e}")
    
    def start_networking(self) -> None:
        """Start networking threads"""
        if self.is_running:
            return
        
        self.setup_sockets()
        self.is_running = True
        self._listener_thread = threading.Thread(target=self._listen_for_collaborators, daemon=True)
        self._listener_thread.start()
    
    def stop_networking(self) -> None:
        """Stop networking"""
        self.is_running = False
        if self._listener_thread and self._listener_thread.is_alive():
            self._listener_thread.join(timeout=2.0)
    
    def broadcast_sync(self, current_time: float) -> None:
        """Broadcast time sync to all collaborators"""
        if not self.sync_sock:
            raise NetworkError("Sync socket not initialized")
        
        payload = json.dumps({
            'type': 'sync',
            'time': current_time,
            'leader_id': 'leader-001',
            'timestamp': time.time()
        })
        
        try:
            self.sync_sock.sendto(payload.encode('utf-8'), (self.BROADCAST_IP, self.SYNC_PORT))
        except Exception as e:
            raise NetworkError(f"Failed to broadcast sync: {e}")
    
    def send_command(self, command: Dict[str, Any], target_pi: Optional[str] = None) -> None:
        """Send command to collaborator Pi(s)"""
        # Add timestamp to command
        command = command.copy()
        command['timestamp'] = time.time()
        payload = json.dumps(command)
        
        try:
            if target_pi and target_pi in self.collaborator_pis:
                # Send to specific Pi
                ip = self.collaborator_pis[target_pi]['ip']
                if not self.control_sock:
                    raise NetworkError("Control socket not initialized")
                self.control_sock.sendto(payload.encode('utf-8'), (ip, self.CONTROL_PORT))
                print(f"📤 Sent command to {target_pi}: {command['type']}")
            else:
                # Broadcast to all Pis
                with self._temp_socket('broadcast') as sock:
                    sock.sendto(payload.encode('utf-8'), (self.BROADCAST_IP, self.CONTROL_PORT))
                    print(f"📡 Broadcast command: {command['type']}")
        except Exception as e:
            raise NetworkError(f"Failed to send command: {e}")
    
    def _listen_for_collaborators(self) -> None:
        """Listen for messages from collaborator Pis"""
        while self.is_running:
            try:
                if not self.control_sock:
                    break
                
                data, addr = self.control_sock.recvfrom(1024)
                msg = json.loads(data.decode('utf-8'))
                
                msg_type = msg.get('type')
                if msg_type == 'register':
                    self._handle_registration(msg, addr)
                elif msg_type == 'heartbeat':
                    self._handle_heartbeat(msg)
                elif msg_type in self.message_handlers:
                    self.message_handlers[msg_type](msg, addr)
                
            except socket.timeout:
                continue
            except json.JSONDecodeError:
                print("⚠️ Received invalid JSON from collaborator")
                continue
            except Exception as e:
                if self.is_running:
                    print(f"❌ Error in collaborator listener: {e}")
    
    def _handle_registration(self, msg: Dict[str, Any], addr: tuple) -> None:
        """Handle collaborator registration"""
        pi_id = msg.get('pi_id')
        if not pi_id:
            print("⚠️ Registration message missing pi_id")
            return
        
        with self._lock:
            self.collaborator_pis[pi_id] = {
                'ip': addr[0],
                'last_seen': time.time(),
                'status': msg.get('status', 'unknown'),
                'video_file': msg.get('video_file', ''),
                'registered_at': time.time()
            }
        print(f"✅ Registered Pi: {pi_id} at {addr[0]}")
    
    def _handle_heartbeat(self, msg: Dict[str, Any]) -> None:
        """Handle collaborator heartbeat"""
        pi_id = msg.get('pi_id')
        if pi_id and pi_id in self.collaborator_pis:
            with self._lock:
                self.collaborator_pis[pi_id]['last_seen'] = time.time()
                self.collaborator_pis[pi_id]['status'] = msg.get('status', 'ready')
    
    def get_connected_collaborators(self) -> Dict[str, Dict[str, Any]]:
        """Get list of connected collaborators with status"""
        current_time = time.time()
        result = {}
        
        with self._lock:
            for pi_id, info in self.collaborator_pis.items():
                info_copy = info.copy()
                last_seen = current_time - info['last_seen']
                info_copy['online'] = last_seen < 5  # Consider online if seen within 5 seconds
                info_copy['last_seen_seconds'] = last_seen
                result[pi_id] = info_copy
        
        return result
    
    def register_message_handler(self, message_type: str, handler: Callable) -> None:
        """Register a custom message handler"""
        self.message_handlers[message_type] = handler


class CollaboratorNetworking(NetworkManager):
    """Networking for collaborator Pi - receives sync and commands"""
    
    def __init__(self, pi_id: str, sync_port: int = 5005, control_port: int = 5006):
        super().__init__(sync_port, control_port)
        self.pi_id = pi_id
        self.is_running = False
        self.sync_handler = None
        self.command_handler = None
        self._sync_thread = None
        self._command_thread = None
        self._heartbeat_thread = None
        self._last_heartbeat = 0
    
    def setup_sockets(self) -> None:
        """Setup collaborator sockets for receiving"""
        with self._lock:
            try:
                # Sync socket for receiving broadcasts
                if not self.sync_sock:
                    self.sync_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    self.sync_sock.bind(('', self.SYNC_PORT))
                    self.sync_sock.settimeout(1.0)
                
                # Control socket for receiving commands
                if not self.control_sock:
                    self.control_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    self.control_sock.bind(('', self.CONTROL_PORT))
                    self.control_sock.settimeout(1.0)
                
            except Exception as e:
                raise NetworkError(f"Failed to setup collaborator sockets: {e}")
    
    def set_handlers(self, sync_handler: Callable, command_handler: Callable) -> None:
        """Set message handlers"""
        self.sync_handler = sync_handler
        self.command_handler = command_handler
    
    def start_networking(self) -> None:
        """Start networking threads"""
        if self.is_running:
            return
        
        self.setup_sockets()
        self.is_running = True
        
        # Start listener threads
        self._sync_thread = threading.Thread(target=self._listen_sync, daemon=True)
        self._command_thread = threading.Thread(target=self._listen_commands, daemon=True)
        self._heartbeat_thread = threading.Thread(target=self._send_heartbeat_loop, daemon=True)
        
        self._sync_thread.start()
        self._command_thread.start()
        self._heartbeat_thread.start()
    
    def stop_networking(self) -> None:
        """Stop networking"""
        self.is_running = False
        
        # Wait for threads to finish
        for thread in [self._sync_thread, self._command_thread, self._heartbeat_thread]:
            if thread and thread.is_alive():
                thread.join(timeout=2.0)
    
    def _listen_sync(self) -> None:
        """Listen for time sync broadcasts"""
        while self.is_running:
            try:
                if not self.sync_sock:
                    break
                
                data, addr = self.sync_sock.recvfrom(1024)
                msg = json.loads(data.decode('utf-8'))
                
                if msg.get('type') == 'sync' and self.sync_handler:
                    self.sync_handler(msg)
                    
            except socket.timeout:
                continue
            except json.JSONDecodeError:
                continue
            except Exception as e:
                if self.is_running:
                    print(f"❌ Error in sync listener: {e}")
    
    def _listen_commands(self) -> None:
        """Listen for commands from leader"""
        while self.is_running:
            try:
                if not self.control_sock:
                    break
                
                data, addr = self.control_sock.recvfrom(1024)
                msg = json.loads(data.decode('utf-8'))
                
                if self.command_handler:
                    self.command_handler(msg, addr)
                    
            except socket.timeout:
                continue
            except json.JSONDecodeError:
                continue
            except Exception as e:
                if self.is_running:
                    print(f"❌ Error in command listener: {e}")
    
    def _send_heartbeat_loop(self) -> None:
        """Send periodic heartbeat to leader"""
        while self.is_running:
            try:
                self._send_heartbeat('running' if self.is_running else 'ready')
                time.sleep(2)  # Heartbeat every 2 seconds
            except Exception as e:
                if self.is_running:
                    print(f"❌ Error in heartbeat loop: {e}")
                time.sleep(5)  # Wait longer before retrying on error
    
    def _send_heartbeat(self, status: str = 'ready') -> None:
        """Send heartbeat to leader"""
        current_time = time.time()
        
        # Rate limit heartbeats to prevent spam
        if current_time - self._last_heartbeat < 1.0:
            return
        
        heartbeat = {
            'type': 'heartbeat',
            'pi_id': self.pi_id,
            'status': status,
            'timestamp': current_time
        }
        
        try:
            with self._temp_socket('broadcast') as sock:
                sock.sendto(json.dumps(heartbeat).encode('utf-8'), (self.BROADCAST_IP, self.CONTROL_PORT))
            self._last_heartbeat = current_time
        except Exception as e:
            raise NetworkError(f"Failed to send heartbeat: {e}")
    
    def register_with_leader(self, video_file: str = None, status: str = 'ready') -> None:
        """Register this Pi with the leader"""
        registration = {
            'type': 'register',
            'pi_id': self.pi_id,
            'status': status,
            'video_file': video_file or '',
            'timestamp': time.time()
        }
        
        try:
            with self._temp_socket('broadcast') as sock:
                sock.sendto(json.dumps(registration).encode('utf-8'), (self.BROADCAST_IP, self.CONTROL_PORT))
            print(f"📤 Registered with leader as '{self.pi_id}'")
        except Exception as e:
            raise NetworkError(f"Failed to register with leader: {e}")
    
    def send_status_update(self, status: str, additional_data: Dict[str, Any] = None) -> None:
        """Send a status update to the leader"""
        status_msg = {
            'type': 'status_update',
            'pi_id': self.pi_id,
            'status': status,
            'timestamp': time.time()
        }
        
        if additional_data:
            status_msg.update(additional_data)
        
        try:
            with self._temp_socket('broadcast') as sock:
                sock.sendto(json.dumps(status_msg).encode('utf-8'), (self.BROADCAST_IP, self.CONTROL_PORT))
        except Exception as e:
            print(f"⚠️ Failed to send status update: {e}")
