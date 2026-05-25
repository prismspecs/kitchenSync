#!/usr/bin/env python3
"""
OSC (Open Sound Control) Handler for kSync
Provides industry-standard control integration (e.g., QLab, Ableton, TouchOSC).
"""

from typing import Dict, Any
from core.logger import log_info, log_error, log_warning

try:
    from pythonosc import udp_client
    OSC_AVAILABLE = True
except ImportError:
    OSC_AVAILABLE = False


class OscHandler:
    """
    Placeholder for the future OSC protocol integration.
    This will allow kSync to send and receive OSC messages
    for synchronization and external hardware control.
    """

    def __init__(self, ip: str = "127.0.0.0", port: int = 9000):
        self.ip = ip
        self.port = port
        self.client = None
        
        if OSC_AVAILABLE:
            self._setup_client()
        else:
            log_warning("python-osc not installed. OSC control disabled.")

    def _setup_client(self):
        try:
            self.client = udp_client.SimpleUDPClient(self.ip, self.port)
            log_info(f"OSC Handler initialized. Sending to {self.ip}:{self.port}")
        except Exception as e:
            log_error(f"Failed to setup OSC client: {e}")

    def send_cue(self, cue: Dict[str, Any]):
        """Send an OSC message based on schedule cue"""
        if not self.client:
            return
            
        address = cue.get("address", "/kitchensync/cue")
        args = cue.get("args", [])
        
        try:
            self.client.send_message(address, args)
            log_info(f"OSC Sent: {address} {args}")
        except Exception as e:
            log_error(f"OSC Send Error: {e}")
