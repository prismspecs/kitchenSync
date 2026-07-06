#!/bin/bash
# Temporarily disable eth0 so git pull uses WiFi (for Pis with Ethernet-only switch).
sudo ip link set eth0 down
git -c http.sslVerify=false pull
sudo ip link set eth0 up

