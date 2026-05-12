# KitchenSync Testing & TDD Workflow

This document outlines how to test KitchenSync across multiple platforms and how to use the "Assisted TDD" framework for verified development.

## 1. Automated Logic Tests (Tier 1)
These tests verify pure Python logic (math, scheduling, state) without hardware. Run these before any commit.

```bash
# Run the core logic tests
python3 tests/test_core.py
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
python3 tools/simulator.py --mode standalone --driver vlc
```

## 3. Distributed Hardware Testing (Tier 3)
Testing between your Desktop and the Raspberry Pi (gSync).

### Scenario A: Pi as Collaborator, Desktop as Leader
1. **On Desktop:** `python3 tools/simulator.py --mode leader`
2. **On Pi:** `python3 collaborator.py --debug`
3. **Verify:** The Pi should report receiving sync from your Desktop IP.

### Scenario B: Pi as Leader, Desktop as Collaborator
1. **On Pi:** `python3 leader.py --debug`
2. **On Desktop:** `python3 tools/simulator.py --mode collaborator`
3. **Verify:** Open `http://DESKTOP_IP:8080` to see real-time drift analysis of your Desktop relative to the Pi.

## 4. The TDD Workflow
When adding a new feature (e.g., OSC Support):

1. **Write a Test:** Add a test case to `tests/` (e.g., `test_osc_send`).
2. **Verify Failure:** Run the test; it should fail (because the code doesn't exist).
3. **Implement:** Write the minimal code to make the test pass.
4. **Human Verification:** Use `tools/simulator.py` to see the results in real-time.
5. **Commit:** Only commit once automated tests pass and human verification is satisfied.

## 5. Web UI Portability
The simulator hosts a tiny web server. You can access this from your phone or any browser on the network to monitor sync health without being tied to a terminal.
- Default: `http://localhost:8080`
- JSON Data: `http://localhost:8080/json`
