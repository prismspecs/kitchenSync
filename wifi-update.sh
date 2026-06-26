#!/bin/bash
# Temporarily disable eth0 so git pull uses WiFi (for Pis with Ethernet-only switch).
sudo ip link set eth0 down
git pull
sudo ip link set eth0 up
