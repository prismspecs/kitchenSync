# Pro-AV Enhancement Roadmap

These are high-priority architectural enhancements to move KitchenSync from a prototype to a professional-grade AV appliance.

## 1. Precision Synchronization (Sub-millisecond)
- **Goal:** Replace UDP broadcast with PTP (IEEE 1588) or GstNetClock.
- **Why:** Eliminates micro-stutters and ensures perfect phase-alignment between nodes.
- **Tech:** `linuxptp`, `GstNetTimeProvider`, `GstNetClientClock`.

## 2. Industry Standard Control (OSC)
- **Goal:** Implement Open Sound Control (OSC) as the primary control protocol.
- **Why:** Allows integration with QLab, Ableton Live, TouchOSC, and professional lighting consoles.
- **Tech:** `python-osc`, `src/protocols/osc_handler.py`.

## 3. System Hardening (Bulletproof Operation)
- **Goal:** Enable "pull-the-plug" safety and auto-recovery.
- **Why:** Protects SD cards from corruption and ensures 24/7 uptime.
- **Tech:** 
    - **OverlayFS:** Read-only root filesystem (enabled via `raspi-config`).
    - **Hardware Watchdog:** Auto-reboot on system hang (via `dtparam=watchdog=on`).

## 4. Zero-Copy Rendering (`kmssink`)
- **Goal:** Render video directly to hardware display planes.
- **Why:** Lowest possible latency and 0% CPU overhead for the display stack.
- **Tech:** GStreamer `kmssink` with `capture-io-mode=4` (DMABUF).
