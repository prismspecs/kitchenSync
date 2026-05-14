# KitchenSync Todo

## Current Cleanup Follow-Up
- [x] Rename remaining `vlc_*` debug labels and log keys to generic player terminology.
- [x] Remove stale VLC wording from deeper docs and debug overlay templates.
- [x] Consolidate setup docs so `setup.sh` is the only documented install path.
- [ ] Decide whether the archived Firefox cleanup flow should be revived or deleted permanently.

## Playback And Sync
- [ ] Add runtime reporting for the active GStreamer sink in the debug overlay.
- [ ] Implement a non-browser based debug overlay for the Collaborator (using a native toolkit like Tkinter or Pygame to avoid browser overhead).
- [ ] Tune collaborator drift control after live hardware measurements.
- [ ] Add a focused sync test that exercises repeated corrections with the mock driver.

## Deployment
- [ ] Add a deployment checklist for Pi imaging, X11 readiness, and USB content validation.

## Backlog
- [ ] Local content caching.
- [ ] Leader web configuration (integrated into remote controller).
- [ ] Multi-channel MIDI improvements.
