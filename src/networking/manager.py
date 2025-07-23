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


class NetworkManager:
    """Base networking functionality"""
    
    def __init__(self, sync_port: int = 5005, control_port: int = 5006):
        self.BROADCAST_IP = '255.255.255.255'
        self.SYNC_PORT = sync_port
        self.CONTROL_PORT = control_port
        self.sync_sock = None
        self.control_sock = None
    
    def setup_sockets(self) -> None:
        """Initialize UDP sockets"""
        try:
            # Sync socket setup varies by role
            self.sync_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            
            # Control socket setup varies by role
            self.control_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            
        except Exception as e:
            print(f"Error setting up sockets: {e}")
            raise
    
    def cleanup(self) -> None:
        """Clean up sockets"""
        try:
            if self.sync_sock:
                self.sync_sock.close()
            if self.control_sock:
                self.control_sock.close()
        except Exception as e:
            print(f"Error during networking cleanup: {e}")


class LeaderNetworking(NetworkManager):
    """Networking for leader Pi - broadcasts sync and manages collaborators"""
    
    def __init__(self, sync_port: int = 5005, control_port: int = 5006):
        super().__init__(sync_port, control_port)
        self.collaborator_pis = {}
        self.is_running = False
        self.message_handlers = {}
    
    def setup_sockets(self) -> None:
        """Setup leader sockets for broadcasting and receiving"""
        try:
            # Sync socket for broadcasting
            self.sync_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sync_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            
            # Control socket for receiving from collaborators
            self.control_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.control_sock.bind(('', self.CONTROL_PORT))
            self.control_sock.settimeout(1.0)
            
        except Exception as e:
            print(f"Error setting up leader sockets: {e}")
            raise
    
    def start_networking(self) -> None:
        """Start networking threads"""
        self.is_running = True
        threading.Thread(target=self.listen_for_collaborators, daemon=True).start()
    
    def stop_networking(self) -> None:
        """Stop networking"""
        self.is_running = False
    
    def broadcast_sync(self, current_time: float) -> None:
        """Broadcast time sync to all collaborators"""
        payload = json.dumps({
            'type': 'sync',
            'time': current_time,
            'leader_id': 'leader-001'
        })
        try:
            self.sync_sock.sendto(payload.encode(), (self.BROADCAST_IP, self.SYNC_PORT))
        except Exception as e:
            print(f"Error broadcasting sync: {e}")
    
    def send_command(self, command: Dict[str, Any], target_pi: Optional[str] = None) -> None:
        """Send command to collaborator Pi(s)"""
        payload = json.dumps(command)
        
        if target_pi and target_pi in self.collaborator_pis:
            # Send to specific Pi
            ip = self.collaborator_pis[target_pi]['ip']
            try:
                self.control_sock.sendto(payload.encode(), (ip, self.CONTROL_PORT))
                print(f"Sent command to {target_pi}: {command['type']}")
            except Exception as e:
                print(f"Error sending command to {target_pi}: {e}")
        else:
            # Broadcast to all Pis
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                sock.sendto(payload.encode(), (self.BROADCAST_IP, self.CONTROL_PORT))
                sock.close()
                print(f"Broadcast command: {command['type']}")
            except Exception as e:
                print(f"Error broadcasting command: {e}")
    
    def listen_for_collaborators(self) -> None:
        """Listen for messages from collaborator Pis"""
        while self.is_running:
            try:
                data, addr = self.control_sock.recvfrom(1024)
                msg = json.loads(data.decode())
                
                if msg.get('type') == 'register':
                    self._handle_registration(msg, addr)
                elif msg.get('type') == 'heartbeat':
                    self._handle_heartbeat(msg)
                
            except socket.timeout:
                continue
            except json.JSONDecodeError:
                print("Received invalid JSON from collaborator")
                continue
            except Exception as e:
                if self.is_running:
                    print(f"Error in collaborator listener: {e}")
    
    def _handle_registration(self, msg: Dict[str, Any], addr: tuple) -> None:
        """Handle collaborator registration"""
        pi_id = msg.get('pi_id')
        if pi_id:
            self.collaborator_pis[pi_id] = {
                'ip': addr[0],
                'last_seen': time.time(),
                'status': msg.get('status', 'unknown')
            }
            print(f"Registered Pi: {pi_id} at {addr[0]}")
    
    def _handle_heartbeat(self, msg: Dict[str, Any]) -> None:
        """Handle collaborator heartbeat"""
        pi_id = msg.get('pi_id')
        if pi_id in self.collaborator_pis:
            self.collaborator_pis[pi_id]['last_seen'] = time.time()
    
    def get_connected_collaborators(self) -> Dict[str, Dict[str, Any]]:
        """Get list of connected collaborators with status"""
        current_time = time.time()
        for pi_id, info in self.collaborator_pis.items():
            last_seen = current_time - info['last_seen']
            info['online'] = last_seen < 5  # Consider online if seen within 5 seconds
        return self.collaborator_pis


class CollaboratorNetworking(NetworkManager):
    """Networking for collaborator Pi - receives sync and commands"""
    
    def __init__(self, pi_id: str, sync_port: int = 5005, control_port: int = 5006):
        super().__init__(sync_port, control_port)
        self.pi_id = pi_id
        self.is_running = False
        self.sync_handler = None
        self.command_handler = None
    
    def setup_sockets(self) -> None:
        """Setup collaborator sockets for receiving"""
        try:
            # Sync socket for receiving broadcasts
            self.sync_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sync_sock.bind(('', self.SYNC_PORT))
            
            # Control socket for receiving commands
            self.control_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.control_sock.bind(('', self.CONTROL_PORT))
            
        except Exception as e:
            print(f"Error setting up collaborator sockets: {e}")
            raise
    
    def set_handlers(self, sync_handler: Callable, command_handler: Callable) -> None:
        """Set message handlers"""
        self.sync_handler = sync_handler
        self.command_handler = command_handler
    
    def start_networking(self) -> None:
        """Start networking threads"""
        self.is_running = True
        threading.Thread(target=self.listen_sync, daemon=True).start()
        threading.Thread(target=self.listen_commands, daemon=True).start()
        threading.Thread(target=self.send_heartbeat, daemon=True).start()
    
    def stop_networking(self) -> None:
        """Stop networking"""
        self.is_running = False
    
    def listen_sync(self) -> None:
        """Listen for time sync broadcasts"""
        while self.is_running:
            try:
                data, addr = self.sync_sock.recvfrom(1024)
                msg = json.loads(data.decode())
                
                if msg.get('type') == 'sync' and self.sync_handler:
                    self.sync_handler(msg)
                    
            except json.JSONDecodeError:
                continue
            except Exception as e:
                if self.is_running:
                    print(f"Error in sync listener: {e}")
    
    def listen_commands(self) -> None:
        """Listen for commands from leader"""
        while self.is_running:
            try:
                data, addr = self.control_sock.recvfrom(1024)
                msg = json.loads(data.decode())
                
                if self.command_handler:
                    self.command_handler(msg)
                    
            except json.JSONDecodeError:
                continue
            except Exception as e:
                if self.is_running:
                    print(f"Error in command listener: {e}")
    
    def send_heartbeat(self) -> None:
        """Send periodic heartbeat to leader"""
        while self.is_running:
            heartbeat = {
                'type': 'heartbeat',
                'pi_id': self.pi_id,
                'status': 'running' if self.is_running else 'ready'
            }
            
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                sock.sendto(json.dumps(heartbeat).encode(), (self.BROADCAST_IP, self.CONTROL_PORT))
                sock.close()
            except Exception as e:
                if self.is_running:
                    print(f"Error sending heartbeat: {e}")
            
            time.sleep(2)  # Heartbeat every 2 seconds
    
    def register_with_leader(self, video_file: str = None) -> None:
        """Register this Pi with the leader"""
        registration = {
            'type': 'register',
            'pi_id': self.pi_id,
            'status': 'ready',
            'video_file': video_file
        }
        
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.sendto(json.dumps(registration).encode(), (self.BROADCAST_IP, self.CONTROL_PORT))
            sock.close()
            print(f"Registered with leader as '{self.pi_id}'")
        except Exception as e:
            print(f"Error registering with leader: {e}")
