# kSync Todo

## Current Cleanup Follow-Up
- [x] Rename remaining `vlc_*` debug labels and log keys to generic player terminology.
- [x] Remove stale VLC wording from deeper docs and debug overlay templates.
- [x] Consolidate setup docs so `setup.sh` is the only documented install path.
- [ ] Decide whether the archived Firefox cleanup flow should be revived or deleted permanently.

## Playback And Sync
- [x] Add runtime reporting for the active GStreamer sink in the debug overlay.
- [x] Implement a non-browser based debug overlay for the Collaborator (using a native toolkit like Tkinter or Pygame to avoid browser overhead).
- [x] Tune collaborator drift control after live hardware measurements.
- [x] Add a focused sync test that exercises repeated corrections with the mock driver.
- [x] Make collaborator sync loop-aware so EOS wrap does not look like a huge drift spike.
- [ ] Implement **Per-Device Latency Compensation** (moving math to Collaborator).
- [ ] Consolidate Heartbeat/Ping into unified **Status Update** protocol.

## UI & Discovery
- [x] Implement **Automated Discovery** (auto-request media/config on join).
- [x] Add **Surgical DOM Reconciliation** for zero-flicker UI updates.
- [x] Replace redundant text buttons with unified **SVG Refresh Icons**.
- [ ] Bystander Status Overlay: Create a visual status screen (IP, ID, Status) for unconfigured nodes to avoid black screens during setup.
