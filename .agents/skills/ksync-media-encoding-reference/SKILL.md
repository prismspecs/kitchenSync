---
name: ksync-media-encoding-reference
description: >
  The kSync content-encoding discipline: which codec each Raspberry Pi model decodes
  in hardware, the per-device file strategy, ffmpeg recipes with 1-second GOPs, and
  how to verify what a device is actually doing. Load this when preparing/converting
  video content, when playback stutters, when a device shows a software-decoder
  warning, or when seeks land far from their target.
---

# kSync Media Encoding Reference

Verified 2026-07-06 against src/video/drivers/gst_driver.py, src/video/file_manager.py,
collaborator.py, and docs/PROJECT_OVERVIEW.md.

When NOT to use: sync math → `ksync-sync-theory-reference`; general playback failures →
`ksync-debugging-playbook`.

## The decode matrix (hardware truth, not preference)

| Device | H.264 | HEVC/H.265 | Rule |
|---|---|---|---|
| Pi 5 (BCM2712) | **No hardware decoder exists.** Software `avdec_h264` only | Hardware via rpivid (`v4l2slhevcdec`/`v4l2slh265dec`) | **Give Pi 5 HEVC files** |
| Pi 4 (BCM2711) | Hardware `v4l2h264dec` — always solid, 1080p60 | Hardware ONLY via stateless `v4l2slh265dec` (needs Bookworm + GStreamer ≥ 1.22); otherwise software = stutter at 1080p | **Give Pi 4 H.264 files** (unless its HEVC HW is verified) |

What the driver does about it (`_reprioritize_decoders`, runs once per process): on a
detected Pi 5 it sets rank 0 on all H.264 hardware factories (they don't exist in
silicon but the plugins register anyway) and on stale HEVC paths, keeping the best
available rpivid HEVC decoder; everywhere it promotes hardware decoders above
software (`avdec_*` demoted below SECONDARY) and promotes glupload/glcolorconvert/
glimagesink for the Pi 5 DMA-buf path. History: this ranking was once inverted and
broke Pi 5 playback (491edc0 → corrected b9e05ad — see ksync-failure-archaeology E6).

## The per-device file strategy

Sync compares **positions**, not content. Nodes may play different encodes of the
same source as long as **fps and duration are identical**. The collaborator's own
configured `video_file` overrides the filename the leader broadcasts
(collaborator.py `_handle_start_command`: `target_file = configured_file or
leader_file`) — that override is the mechanism that makes per-device codecs work.

Standard naming: `<content>_pi5_hevc.mp4` and `<content>_pi4_h264.mp4`.

## The recipes (encode both from the SAME source)

```bash
# Pi 4 — H.264 hardware decode:
ffmpeg -i SOURCE -an -vf "fps=30,format=yuv420p" \
  -c:v libx264 -profile:v high -level 4.2 -preset slow \
  -x264-params keyint=30:min-keyint=30:scenecut=0 \
  -b:v 10M -maxrate 12M -bufsize 20M \
  content_pi4_h264.mp4

# Pi 5 — HEVC hardware decode:
ffmpeg -i SOURCE -an -vf "fps=30,format=yuv420p" \
  -c:v libx265 -preset medium -tag:v hvc1 \
  -x265-params keyint=30:min-keyint=30:scenecut=0 \
  -b:v 10M -maxrate 12M -bufsize 20M \
  content_pi5_hevc.mp4
```

Flag rationale: `-an` audio off (installations run silent; enable_audio=false);
`fps=30` forces identical CFR timing on both outputs (change BOTH `fps=` and
`keyint`/`min-keyint` together — keyint must equal fps); `format=yuv420p` = the only
pixel format the Pi hardware decoders accept; `keyint=30:min-keyint=30:scenecut=0` =
exactly one keyframe per second, no surprise scene-cut keyframes; `-tag:v hvc1` =
HEVC fourcc some demuxers require; bitrate caps sized for Pi USB/SD read + decode
headroom at 1080p30.

**Why 1-second GOPs are load-bearing**: fast catch-up seeks are KEY_UNIT (snap to
the nearest keyframe). Stock long-GOP downloads snapped to 0:00 and the collaborator
hovered there until the leader looped (fixed to escalate in cb09752, but ACCURATE
seeks into long GOPs decode from the previous keyframe — seconds of stall on a Pi).
Dense keyframes make every seek land within ~0.5 s at negligible cost at these
bitrates.

## Verification workflow

```bash
# 1. What is this file, really?
gst-discoverer-1.0 media/content_pi5_hevc.mp4      # expect: video #N: H.265 ...

# 2. What is the device actually using? (on the device, after playback started)
grep -E "Active hardware decoder|PERFORMANCE WARNING" ~/kitchenSync/logs/kitchensync.log | tail -3
# Good Pi 4: Active hardware decoder 'v4l2h264dec'
# Bad:       PERFORMANCE WARNING: Using software decoder 'avdec_h265'

# 3. What decoders does this device have at all?
gst-inspect-1.0 | grep -E "v4l2(sl)?h?(264|265|evc)"

# 4. Full environment probe (script ships in repo):
.venv/bin/python tools/verify_gst_hwaccel.py
```

Metadata pipeline (src/video/file_manager.py `get_metadata`): python GstPbutils
Discoverer → `gst-discoverer-1.0` CLI → `ffprobe`, cached by (path, mtime).
`is_optimized` simply means "video codec is HEVC" and feeds the web-UI HEVC badge.
History: the CLI fallback once mis-parsed modern output ("h.265" with a dot) so the
same file was labeled differently per device (fixed cdc43a7); the leader's badge was
also hardcoded false (fixed 5570b2d). If a device lacks `gst-discoverer-1.0`
(log: `Metadata CLI discovery failed`), labels may degrade — playback is unaffected.

Current test media in `media/` (verified 2026-07-06, not in git): sync_test_definitive.mp4
(HEVC 1080p30, 30.000 s), sync_test_definitive_h264.mp4 (H.264 1080p30), bbb_* demo
files (long-GOP — useful for reproducing seek pathologies, not for shows).

## Future (candidate, owner-confirmed, low priority)

Drag-and-drop auto-transcode UI running these recipes per target device (Electron
skin or browser addition) — see `ksync-research-frontier`. Until then, encoding is a
manual pre-show step.

## Provenance and maintenance

Written 2026-07-06. Re-verify:
- Ranking logic: `grep -n "_reprioritize_decoders" -A 40 src/video/drivers/gst_driver.py | head -50`
- Override still holds: `grep -n "configured_file or leader_file" collaborator.py`
- Recipes match docs: `grep -n "keyint=30" docs/PROJECT_OVERVIEW.md`
- Media inventory: `for f in media/*.mp4; do echo "$f"; gst-discoverer-1.0 "$f" 2>/dev/null | grep "video #"; done`
