# Code Archive

This folder holds files that were removed from the active runtime path during cleanup but were not deleted outright.

Known-good baseline before cleanup:
- Git tag: `good-working-2026-05-12`
- Commit: `f113d9672691d13af9adb69bb11ac2f77c3dfb2e`

Archived items:
- `setup/setup_legacy.sh`: old mixed VLC/Wayfire/PCManFM setup script replaced by the active Pi 5 Openbox setup flow.
- `scripts/cleanup_logs.sh`: duplicated by the log-archiving logic already present in `start_clean.sh`.
- `scripts/cleanup_firefox.sh`: legacy maintenance helper not part of the active runtime path.
- `arduino/midi_controller-workingserial/`: alternate Arduino controller variant retained for reference because its behavior differs from the primary sketch.