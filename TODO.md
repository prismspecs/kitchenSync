# KitchenSync Todo

## 🚨 Critical Priority: Video Player Replacement
The current VLC-based player lacks the low-level control needed for seamless synchronization.
- [ ] **Research & Prototype GStreamer Pipeline**
    - Target: Hardware accelerated playback on Pi (`v4l2h264dec` or `mmal`).
    - Feature: Rate control (playback speed) without pitch shifting (optional, or just allow pitch shift for micro-corrections).
    - Feature: Instant seeking without buffer flushing.
- [ ] **Implement `GstPlayer` Class**
    - Create `src/video/gst_player.py`.
    - Implement standard interface: `load`, `play`, `pause`, `seek`, `get_position`, `set_rate`.
- [ ] **Update `collaborator.py` Sync Logic**
    - Move from "Stop-Seek-Wait" to "Rate Adjustment" (PID controller approach).
    - If drift < 1s: Adjust speed (e.g., 1.05x).
    - If drift > 1s: Hard seek.

## 🛠 Features & Improvements
- [ ] **Local Content Caching**
    - Copy videos from USB to local SD/SSD on boot to improve read performance and seeking.
    - Verify checksums to avoid re-copying unchanged files.
- [ ] **Leader Web Config**
    - Allow setting volume and schedule via the web interface.
- [ ] **Openbox / Display Setup**
    - Verify `cleanup_firefox.sh` and display scripts for production deployment.

## 🐛 Bugs & Maintenance
- [ ] Refactor `TODO.md` (Done).
- [ ] Clean up `src/networking` to handle packet loss more gracefully.

## 📝 Backlog / Ideas
- [ ] Mobile App for management.
- [ ] Multi-channel MIDI support improvements.
