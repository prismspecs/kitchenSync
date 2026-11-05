# kSync Todo

Completed items are pruned — history lives in CHANGELOG.md and git log.
The active technical campaign is `.agents/skills/ksync-sub10ms-campaign`;
cleanup execution follows `docs/CLEANUP_REPORT.md`.

## Open

- [ ] Local content caching (`enable_caching` is a stub).
- [ ] Multi-channel MIDI improvements (feature dormant; see docs/MIDI_CONTROL.md).
- [ ] Bystander Status Overlay: visual status screen (IP, ID, status) for
      unconfigured nodes so setup never shows a black screen.
- [ ] Calibration wizard / per-device auto-transcode UI (deferred — see
      `.agents/skills/ksync-research-frontier` F2/F4).
- [ ] x86 mini PC (`ksync-pc1`, experimental; see `docs/INSTALLATION.md` → Mini PC):
  - [ ] Sync test against a Pi, using `logs/sync_deviation.csv` (no Pi was running on 2026-11-05).
  - [ ] Clean 4K60 playback:
    - Decode has headroom, so the loss is in the display path.
    - Things to try: the GPU perf level, a video-only native playbin (`flags=0x41`) with the VA path, and kSync's own sink bin, which hasn't been measured.
    - Test on a real 4K screen.
  - [ ] Leader hotspot on the Realtek RTL8821CE (it reports AP mode support, but hosting hasn't been tested).
  - [ ] USB provisioning (`ksync.ini` on a stick) via the new `/media/usb-*` auto-mount.
  - [ ] Multi-screen output (3×1080p or 1×4K).
  - [ ] PCs have no device tree, so `pi_model` is empty. The web UI shows no model, and auto-transcode falls back to HEVC, which is fine on AMD. The proper fix is ROADMAP A0 (`platform` + `decode_profile`).
