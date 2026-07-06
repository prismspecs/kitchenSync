---
name: gstreamer-hwaccel-verify
description: >
  Verify GStreamer hardware acceleration status on Raspberry Pi for kSync.
  Wraps tools/verify_gst_hwaccel.py with diagnostic interpretation, expected
  decoder/sink combinations per Pi model, and troubleshooting for common
  HW accel failures.
---

# kSync GStreamer Hardware Acceleration Verifier

Use this skill when:
- Setting up a new Pi and need to confirm HW accel works
- Video playback is slow or dropping frames
- The debug overlay shows software decode instead of hardware
- After OS updates that may change GStreamer plugin availability

## Quick Verification

```bash
# Full verification with JSON output (recommended)
DISPLAY=:0 XDG_SESSION_TYPE=x11 python3 tools/verify_gst_hwaccel.py --video media/sync_test.mp4 --json

# Quick codec probe (no video file needed)
gst-inspect-1.0 | grep -E '(v4l2h264dec|v4l2slh265dec|avdec_h264)'
```

## Expected Results by Platform

### Raspberry Pi 5
```json
{
  "active_decoder": "v4l2slh265dec",  // For H.265 content
  "active_sink": "glimagesink",
  "hw_accel": true,
  "gpu_memory_mb": 256
}
```
For H.264 content: `"active_decoder": "v4l2h264dec"`

### Raspberry Pi 4B
```json
{
  "active_decoder": "v4l2h264dec",    // H.264 only
  "active_sink": "glimagesink",
  "hw_accel": true,
  "gpu_memory_mb": 256
}
```
Note: Pi 4B does NOT have hardware H.265 decoding.

### Desktop (Development)
```json
{
  "active_decoder": "avdec_h264",     // Software decode
  "active_sink": "autovideosink",
  "hw_accel": false
}
```
This is expected for desktop development — use the mock driver for sync testing.

## Diagnostic Flowchart

```
Is GStreamer installed?
├── NO → sudo apt install gstreamer1.0-plugins-{base,good,bad,ugly} gstreamer1.0-libav
└── YES
    ↓
Does gst-inspect-1.0 show v4l2h264dec?
├── NO → Check GPU memory: vcgencmd get_mem gpu (need 256+)
│   ├── GPU < 256 → raspi-config → Performance → GPU Memory → 256
│   └── GPU ≥ 256 → Check kernel: ls /dev/video* (need video10-12 for codec)
│       ├── No /dev/video1x → Kernel module missing, try: sudo modprobe bcm2835-codec
│       └── Devices exist → Plugin not installed: sudo apt install gstreamer1.0-plugins-bad
└── YES
    ↓
Does playback show "HW Accel: ACTIVE" in debug overlay?
├── NO → Check DISPLAY variable: echo $DISPLAY
│   ├── Empty → export DISPLAY=:0 or add to systemd service
│   └── Set → Check video format: gst-discoverer-1.0 your_video.mp4
│       └── If HEVC on Pi 4 → No HW decode available, re-encode to H.264
└── YES → ✅ All good
```

## GStreamer Sink Fallback Chain

The kSync GstDriver tries sinks in this order:
1. `glimagesink` — OpenGL ES (preferred, lowest latency with HW decode)
2. `autovideosink` — GStreamer's automatic selection
3. `xvimagesink` — X11 Video Extension (older, compatible)
4. `fakesink` — No display output (headless/CI mode)

If the driver falls back to `fakesink`, sync mode switches to `wall` clock.

## Runtime Verification

During playback, check the debug overlay or log for:
```
Gst: Using hardware-preferred video sink 'glimagesink'
```

If you see this instead, HW accel is NOT active:
```
Gst: Falling back to autovideosink
```

## Video Encoding Guidelines

For best HW accel compatibility:
- **Pi 4B:** H.264 High Profile, Level 4.2, max 1080p60 or 4K30
- **Pi 5:** H.265 Main Profile OR H.264 High Profile
- **Container:** MP4 (not MKV, for fastest parse startup)
- **Audio:** AAC or no audio (avoid AC3/DTS — decoder overhead)

```bash
# Re-encode for Pi compatibility (H.264, high quality)
ffmpeg -i input.mov -c:v libx264 -preset slow -crf 18 -profile:v high -level 4.2 -c:a aac output.mp4

# Re-encode for Pi 5 H.265
ffmpeg -i input.mov -c:v libx265 -preset slow -crf 20 -c:a aac output_h265.mp4
```
