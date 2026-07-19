# kSync Testing & TDD Workflow

This document outlines how to test kSync across multiple platforms and how to use the "Assisted TDD" framework for verified development.

## 1. Automated Logic Tests (Tier 1)
These tests verify pure Python logic (math, scheduling, state) without hardware. Run these before any commit.

```bash
# Run the core logic tests
python3 -m unittest tests.test_core
python3 -m unittest tests.test_networking
python3 -m unittest tests.test_sync_regressions
```

## 2. Cross-Platform Simulator (Tier 2)
The `tools/simulator.py` script allows you to test the distributed system on your desktop (Windows/macOS/Linux) using a `Mock` video driver.

### Leader Simulation (Desktop acting as Leader)
```bash
python3 tools/simulator.py --mode leader --driver mock
```
- Starts broadcasting UDP sync on port 5005.
- Provides a Web UI at `http://localhost:8080`.

### Collaborator Simulation (Desktop acting as Collaborator)
```bash
python3 tools/simulator.py --mode collaborator --driver mock
```
- Listens for sync packets.
- Simulates its own clock and prints "Drift" relative to the leader.

### Standalone Mode (Just play video)
```bash
python3 tools/simulator.py --mode standalone --driver gst
```

## 3. Distributed Hardware Testing (Tier 3)
Testing between your Desktop and the Raspberry Pi (gSync).

### Scenario A: Pi as Collaborator, Desktop as Leader
1. **On Desktop:** `python3 tools/simulator.py --mode leader`
2. **On Pi:** start X first with `./tools/start_x.sh` if no local session is already running.
3. **On Pi:** `DISPLAY=:0 python3 collaborator.py --config collaborator_config.ini --debug`
4. **Verify:** The Pi should report receiving sync from your Desktop IP.

### Scenario B: Pi as Leader, Desktop as Collaborator
1. **On Pi:** start X first with `./tools/start_x.sh` if no local session is already running.
2. **On Pi:** `DISPLAY=:0 python3 leader.py --config ksync_webui.ini --debug`
3. **On Desktop:** `python3 tools/simulator.py --mode collaborator`
4. **Verify:** Open `http://DESKTOP_IP:8080` to see real-time drift analysis of your Desktop relative to the Pi.

## 3.5 Loop Boundary Validation
Looping is a special sync case because the leader and collaborator both loop locally on EOS instead of receiving a dedicated network "loop" command.

What we learned:
- The leader broadcasts wrapped media position from `get_position()`, so the loop boundary is not monotonic wall-clock time.
- The Gst driver can briefly expose a stale near-end cached position while the EOS seek to `0` is settling unless that cache is reset immediately.
- The collaborator must compare positions on a wrapped timeline; otherwise `9.98s` versus `0.03s` looks like a huge drift and triggers an unnecessary hard seek.

Manual loop test:
1. Use a short looping clip such as `videos/sync_test.mp4`.
2. Start leader and collaborator in debug mode.
3. Let the clip loop several times.
4. Verify that the collaborator does not log a large sync deviation or immediate hard seek right after EOS.
5. If you enable raw deviation logging, expect small signed errors across the seam instead of a jump close to full clip duration.

## 4. Hardware Acceleration Check

On the Pi, start X first if needed:

```bash
./tools/start_x.sh
```

Then run the verifier:

```bash
DISPLAY=:0 XDG_SESSION_TYPE=x11 python3 tools/verify_gst_hwaccel.py --video videos/test265.mp4 --json
```

For Pi 5 HEVC decode, the verification target is:

```text
"active_decoder": "v4l2slh265dec"
```

For runtime playback, start leader or collaborator in debug mode and verify the GStreamer sink log:

```text
Gst: Using hardware-preferred video sink 'glimagesink'
```

If the log reports a fallback sink instead, acceleration is not fully confirmed on that node.

## 5. The TDD Workflow
When adding a new feature (e.g., OSC Support):

1. **Write a Test:** Add a test case to `tests/` (e.g., `test_osc_send`).
2. **Verify Failure:** Run the test; it should fail (because the code doesn't exist).
3. **Implement:** Write the minimal code to make the test pass.
4. **Human Verification:** Use `tools/simulator.py` to see the results in real-time.
5. **Commit:** Only commit once automated tests pass and human verification is satisfied.

Focused loop regression command:

```bash
pytest tests/test_sync_regressions.py tests/test_sync_simulation.py
```

## 6. Web UI Portability
The simulator hosts a tiny web server. You can access this from your phone or any browser on the network to monitor sync health without being tied to a terminal.
- Default: `http://localhost:8080`
- JSON Data: `http://localhost:8080/json`

## 7. WiFi Provisioning (real-hardware checklist)

Unit tests (`tests/test_wifi_manager.py`, `tests/test_captive_portal.py`)
cover the decision logic; AP mode and the portal can only be proven on real
Pis. Run these four scenarios before an unattended deployment
(design: [WIFI_PROVISIONING.md](WIFI_PROVISIONING.md)):

1. **Zero-config cluster:** boot leader + collaborator with no ethernet and
   no saved WiFi. Expect `kSync-<cluster_name>` to appear within ~1 min and
   the collaborator to join and sync with no interaction. Boot order must
   not matter (start the collaborator first to confirm).
2. **Portal flow:** join the hotspot with a phone — the setup page must
   open automatically (fallback `http://10.42.0.1`). Submit real venue
   credentials; expect the ack counter to reach N/N and all devices to
   reappear on the venue network within ~1 min, still syncing.
3. **Wrong-password recovery:** submit bad credentials; expect
   `kSync-<cluster_name>` to return by itself within ~3 min with sync
   restored. This is the "cannot be bricked" guarantee.
4. **Two clusters, one room:** two leaders with different `cluster_name`s;
   each collaborator must join only its own cluster's SSID.

Useful on-device commands:

```bash
nmcli device                      # interface states
nmcli -f NAME,TYPE connection show # ksync-hotspot / ksync-cluster / ksync-venue-wifi
journalctl -u kitchensync.service | grep -i wifi
```
