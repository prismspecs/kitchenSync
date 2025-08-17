import socket

UDP_IP = "0.0.0.0"  # Listen on all interfaces
UDP_PORT = 5005  # Change to your leader signal port

print(f"Listening for leader signals on UDP port {UDP_PORT}...")

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind((UDP_IP, UDP_PORT))

try:
    while True:
        data, addr = sock.recvfrom(1024)
        print(f"Received from {addr}: {data.decode(errors='ignore')}")
except KeyboardInterrupt:
    print("Stopped listening.")
finally:
    sock.close()
