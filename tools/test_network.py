#!/usr/bin/env python3
"""
KitchenSync Network Diagnostic Tool
Tests UDP connectivity between Leader and Collaborator.
"""

import socket
import sys
import time
import argparse

def run_sender(ip, port):
    print(f"🚀 Sending test packets to {ip}:{port}...")
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    if ip.endswith(".255") or ip == "255.255.255.255":
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    
    count = 0
    try:
        while True:
            count += 1
            msg = f"TEST_PACKET_{count}_{time.time()}"
            sock.sendto(msg.encode(), (ip, port))
            print(f"  Sent: {msg}")
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopped.")

def run_receiver(port):
    print(f"👂 Listening for test packets on port {port}...")
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("", port))
    
    try:
        while True:
            data, addr = sock.recvfrom(1024)
            print(f"  Received from {addr}: {data.decode()}")
    except KeyboardInterrupt:
        print("\nStopped.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Network Diagnostic")
    parser.add_argument("mode", choices=["send", "recv"])
    parser.add_argument("--ip", default="255.255.255.255", help="Target IP for sender")
    parser.add_argument("--port", type=int, default=5005, help="UDP port")
    
    args = parser.parse_args()
    
    if args.mode == "send":
        run_sender(args.ip, args.port)
    else:
        run_receiver(args.port)
