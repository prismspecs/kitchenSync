# KitchenSync Project

## Overview
KitchenSync enables synchronized video playbook and GPIO relay control across multiple Raspberry Pis on a local network. One Pi acts as the leader, broadcasting synchronized time via UDP and serving as a user interface for control and configuration. Collaborator Pis use this signal to start video playback with `omxplayer` and trigger relays at pre-defined timecodes. Each Pi has a unique ID and can play different videos (or the same video as needed). Videos can be stored locally on each device or played from USB drives. The system uses lightweight UDP time sync and Python threading for concurrency.

## Stack
- **Language:** Python 3
- **Media Player:** omxplayer
- **Networking:** UDP broadcast (Python `socket` module)
- **Hardware:** Raspberry Pi + relay module (via GPIO)
- **Sync Method:** Leader Pi broadcasts time; collaborator Pis offset their clocks
- **Device Management:** Each Pi has unique ID; can play different or identical videos
- **Video Sources:** Local storage or USB drives
- **User Interface:** Leader Pi provides control interface for configuration and file management
- **Schedule Format:** JSON
- **Concurrency:** `threading.Thread` for non-blocking network listening