# kSync Roadmap

For day-to-day open items, see `TODO.md`. The active technical campaign
(sub-10ms sync) takes priority over everything here unless stated otherwise.

---

## Vision

kSync runs in two forms:

1. **As an appliance**: a Raspberry Pi 5 with the software pre-loaded. This is
   the product's identity and the primary target.
2. **As software**: installable on **Linux, macOS, and Windows**. A laptop can be
   a leader, a collaborator, or the only node in the show.

### Guiding principles

- **Pi-first development.** Build, test, and optimize on Pi hardware. The
  software must stay lean enough to run well on a Pi without depending on Mac
  (or any desktop) hardware. The Pi must never regress so another platform can
  gain.
- **One unified interface.** The control UI stays a web server running on the
  leader. On a Pi cluster, you open it in a browser. On a MacBook that is the
  only node, you open the same UI in a browser, or later in a thin desktop
  wrapper. There is one UI codebase.
- **Portability by inverting dependencies.** Put interfaces at the leaves
  (video driver, platform services). Do not layer a portable framework on top.
  An abstraction designed for the average of three platforms ends up worse than
  native on all three. Add an abstraction only once two real implementations
  exist to justify it.
- **The UI is a client, never the owner of state.** A Pi cluster must run with
  no UI host present. This is an existing architecture invariant, and nothing
  on this roadmap may break it.
- **Measure, don't eyeball.** Every cross-platform sync claim is backed by
  `logs/sync_deviation.csv`.

---

## Where we are today

The codebase is already shaped for portability:

- There is no `platform.system()` / `sys.platform` branching in `src/` or the
  entry points.
- The `VideoDriver` ABC (`src/video/driver.py`) covers the full playback
  contract: load/play/pause/seek/set_speed/get_position/set_fullscreen.
- GStreamer lives in one file, `src/video/drivers/gst_driver.py`, plus a lazy
  `import gi` in `src/video/file_manager.py`.
- Linux-only concerns are already separate modules:
  `src/networking/wifi_manager.py` (nmcli), `src/networking/captive_portal.py`
  (dnsmasq), `src/ui/window_manager.py` (X11/Wayland), and
  `src/core/node_common.py` (systemctl reboot).
- `mock_driver.py` lets the test suite run on any OS without GStreamer, so the
  cross-platform CI story is already built.

### The real gaps

**1. The ABC is a playback seam, not a sync seam.** The netclock path (the
precision path) reaches past the abstraction using duck typing:

- `leader.py:325`: `hasattr(self.video_player, "get_pipeline_base_time")`
- `collaborator.py:620`: `getattr(self.video_player, "_net_clock", None)`,
  which reaches into a private attribute
- `collaborator.py:681`: `hasattr(self.video_player, "netclock_realign")`
- `collaborator.py:759`: `hasattr(self.video_player, "use_network_clock")`

`get_pipeline_base_time`, `use_network_clock`, `netclock_realign`, and
`get_pipeline_clock` are defined only on `GstDriver`. So the part of the system
we care most about is the least abstracted.

**2. Pi concepts have leaked into the protocol and UI.** `pi_model` travels in
registration and heartbeats (`src/networking/communication.py`), and
`src/remote/controller.py::_get_target_codec` picks a codec by matching
`"Raspberry Pi 4"` in that string. `is_optimized` has the same problem.

The fix is to reframe `is_optimized` as the general primitive rather than
treating it as a Pi liability. Every platform needs to know whether a file
matches the device's fast decode path: rpivid HEVC on a Pi 5, VideoToolbox
H.264/HEVC on a Mac, D3D11 decoding on Windows. The per-device codec strategy
is already the platform-agnostic media strategy; it just has a Pi-specific
name. Generalize it to **"this file matches this node's decode profile"** by
replacing `pi_model` with a `platform` + `decode_profile` pair, and the
cross-platform content story follows directly.

---

## Track A: Platform agnosticism

### A0: Pure refactor, zero behavior change *(do this regardless)*

This work is safe, cheap, and reversible, and it pays off even if we never port
anything.

- [ ] Add the netclock surface to the `VideoDriver` ABC:
      `get_pipeline_base_time`, `use_network_clock`, `netclock_realign`,
      `get_pipeline_clock`, plus a declared `supports_netclock` capability.
      Remove the `hasattr` / `_net_clock` leaks in `leader.py` and
      `collaborator.py`.
- [ ] Extract a thin `src/platform/` module for reboot, display environment,
      hardware/model probe, and data/config paths. It gets one Linux
      implementation now, and others only when they are real.
- [ ] Generalize `pi_model` → `platform` + `decode_profile` in the wire
      protocol. Keep reading `pi_model` for backward compatibility with older
      nodes during the transition.
- [ ] Add a guard test that forbids `v4l2|nmcli|systemctl|/proc/|/sys/`
      outside the allowed directories (`src/platform/`, `src/networking/`,
      `src/video/drivers/`). This matches the existing invariant-test style.
- [ ] Confirm the full test suite passes on macOS and Windows using
      `mock_driver` (CI job, no GStreamer).

Pi behavior stays the same. As a side effect, the netclock path gets sturdier.

### A1: Feasibility spike *(one day, go/no-go gate)*

Collect facts before promising anything.

- [ ] Verify the official GStreamer Python wheels (`gstreamer-bundle`, 1.28+)
      on macOS and Windows.
- [ ] Confirm `GstNet` / `GstNetClientClock` / `GstNetTimeProvider` are
      present and work in those wheels. The netclock path depends on this.
- [ ] Confirm broadcast UDP (discovery + heartbeats) works through the
      **macOS Local Network permission** prompt. Since macOS 15 this needs user
      consent, and in some non-App-Store packaging styles the prompt reportedly
      never appears, which silently blocks discovery.
- [ ] Confirm the same through the **Windows Defender Firewall** first-bind
      prompt (inbound is blocked by default).
- [ ] Note licensing: `gstreamer-bundle` pulls in GPL / patent-encumbered
      plugins by default. The `gstreamer-meta` variant keeps those behind
      opt-in extras. If kSync ships as a distributed product, make this call
      on purpose.
- [ ] Note that the wheels are per-Python-version (not abi3), so packaging
      must pin the interpreter.

### A2: macOS collaborator joining a Pi leader

- Software decode is fine, and we make no HW-accel claims yet.
- This proves the sync core and netclock are portable with minimal packaging
  risk.
- Success criterion: sync deviation in line with a Pi collaborator, measured
  in `logs/sync_deviation.csv`.

### A3: Single-node leader on macOS / Windows

- This is the "MacBook is the only device" case. Sync risk is low (no peers),
  but packaging, permissions, and service risk are high.
- Make **N=0 collaborators a tested path**, not something that happens to
  work. The leader must not block or degrade when it has no peers.
- The control UI is served by the leader and opened in the browser, exactly as
  on a Pi.

### A4: macOS / Windows leader with Pi collaborators

- This is the real test. The risk is leader timing jitter degrading every
  node.
- Measure with `logs/sync_deviation.csv`.

### A5: Hardware-accelerated decode per platform

- Map decode elements: `v4l2h264dec` / rpivid → `vtdec` (macOS) /
  `d3d11h264dec`, `d3d11h265dec` (Windows).
- Choose sinks per platform (`glimagesink` / `osxvideosink` / `d3d11videosink`).
- Give each platform a `decode_profile` so auto-transcode targets the right
  codec per node.
- This work is mechanical, and it is the easy part.

### A6: Desktop wrapper *(optional, last)*

- **Build a PWA first**: manifest, service worker, install prompt, and
  fullscreen. That gets most of the "it's an app" feel on every OS with zero
  packaging work.
- Consider Electron/Tauri only if the PWA falls short. If we build one:
  - It must be a **configurable-endpoint shell**, not a localhost-only one.
    It either finds a leader on the LAN through the existing UDP discovery
    (`discover` / `leader_announce`) or starts a local one.
  - **It must never be the only path to the UI.** The browser always works.
- The Pi image stays the flagship. Spend packaging effort there first.

### Where the cost actually is

Ranked by real effort. None of these is the sync math, which ports cleanly:

1. **Windows packaging + firewall**: installer, code signing, auto-update, and
   firewall rules. This is the most expensive platform.
2. **macOS Local Network permission + notarization**: test early, so we don't
   discover problems in month three.
3. **Process supervision + windowing**: systemd → launchd / scheduled task.
   `DISPLAY` handling and `window_manager.py` (wmctrl/wlrctl) have no
   macOS/Windows equivalent and need per-platform sink/positioning code.
4. **Testing matrix**: 3 OSes × 2 roles × HW/SW decode. This is a recurring
   cost, not a one-time port.
5. **GStreamer element mapping**: real work, but mechanical.

> Platform agnosticism is mostly a **maintenance-budget decision**. As a
> refactor (A0), it doesn't compete with the sub-10ms campaign. It starts
> competing hard once we own three installers, three auto-update paths, and a
> signing matrix. Gate A3+ on the campaign being in a good place.

---

## Track B: Plugins

Plugins extend what a show can do without growing the core. The first
motivating plugin is **captions**: text written onto the screen, generated by
automatic transcription with Whisper.

### Design principles

- **Plugins run out-of-process.** A plugin that crashes, leaks, or burns CPU
  must not be able to disturb playback or sync. The core supervises plugin
  processes and talks to them over a local socket/IPC.
- **Plugins can run on any node, including a non-playing one.** kSync is
  already distributed, so a heavy plugin such as live Whisper can run on a
  laptop or a dedicated Pi. It sends its output (caption events) over the
  network to the nodes that render it. The Pi players only draw text, which is
  cheap.
- **On a Pi, plugins get a strict resource budget**: `nice`, cgroup CPU
  limits, and optionally pinning to a core that the decode/sync threads don't
  use. The Pi-first rule still holds: an enabled plugin must not measurably
  worsen `sync_deviation.csv`.
- **Start with the smallest API that serves two real plugins.** Don't design a
  general framework up front. Build captions plus one other plugin, then
  extract the shared shape.

### Plugin kinds (initial sketch)

| Kind | What it does | Example |
|---|---|---|
| **Overlay** | Supplies content rendered over the video, timed either to media position or to wall-clock/live events | Captions, lower-thirds, clock, show info |
| **Media processor** | Runs on content at import/transcode time | Offline transcription → `.srt`, thumbnail generation |
| **Control / trigger** | Reacts to or emits show events | OSC/MIDI bridges, cue triggers, schedule actions |

A plugin declares a manifest (name, version, kinds, resource needs, and which
nodes it runs on). The web UI lists installed plugins, lets you enable or
configure them per show and per node, and shows their health.

### Rendering overlays

- Keep overlay rendering inside the existing GStreamer pipeline, e.g. a
  `textoverlay` / `cairooverlay` element in `playbin`'s `video-filter`, or
  inside the GL sink bin before `glupload`. It must stay on the
  hardware-accelerated path, so verify that GPU/CPU cost on a Pi 5 is
  negligible.
- Overlays that are keyed to media position (subtitles) are **automatically
  in sync on every node**, because they ride on the synced playback position.
  Live overlays are keyed to the leader's clock and broadcast as timestamped
  events.

### Captions / Whisper: two very different problems

1. **Pre-recorded captions (easy, do first).** Transcribe each video once, at
   upload or transcode time, into a subtitle track (`.srt` / WebVTT) stored
   next to the media. Every node renders the subtitles by media position, so
   they are frame-synced across the cluster for free. On a Pi 5,
   `whisper.cpp` with a small model (tiny/base) is slower than real time but
   perfectly fine as a background job. The job can also run on a faster
   machine and send the `.srt` back. Captions stay editable in the UI before
   the show.
2. **Live captions from a microphone (hard, do later).** This means real-time
   streaming transcription. A Pi 5 is marginal for this: tiny/base models can
   roughly keep up, but with several seconds of latency and weaker accuracy,
   and it competes with playback for CPU. The recommended setup is to run the
   live-Whisper plugin on a **separate machine** (laptop or dedicated Pi) that
   broadcasts caption events. Player Pis only render them.
   - [ ] Spike: benchmark `whisper.cpp` (tiny.en / base.en, quantized) on a
         Pi 5 while it is *also* playing 4K, and record the impact on sync
         deviation.

### Plugin milestones

- [ ] **B0**: Overlay primitive in the video driver (draw text at a position,
      style, show/hide) plus a subtitle-track renderer. No plugin system yet.
- [ ] **B1**: Offline transcription job (`whisper.cpp`) that produces
      subtitles at import. UI to enable it, review, and edit.
- [ ] **B2**: Extract the plugin host: manifest, out-of-process supervisor,
      IPC, resource limits, and UI listing. Port B1 onto it.
- [ ] **B3**: A second, different plugin (e.g. lower-thirds / text cue, or an
      OSC trigger bridge) to validate the API.
- [ ] **B4**: Live captions plugin running on a non-player node,
      broadcasting timestamped caption events.
- [ ] **B5** *(later)*: Third-party plugin install/packaging story.

---

## Track C: Pi pro-AV hardening

Folded in from the former `docs/ROADMAP.md`. These are Pi-specific
professional-AV upgrades, independent of the portability and plugin tracks
above.

- [ ] **Precision sync via PTP/GstNetClock.** Replace UDP broadcast timing
      with `GstNetTimeProvider` / `GstNetClientClock` (or IEEE 1588 `linuxptp`)
      to eliminate micro-stutters and get tighter phase-alignment between
      nodes. This is the same netclock path called out in A0 — landing the ABC
      surface there is a prerequisite for building this out further.
- [ ] **OSC control.** Add Open Sound Control as a control protocol
      (`python-osc`, `src/protocols/osc_handler.py`) so kSync can be driven
      from QLab, Ableton Live, TouchOSC, and lighting consoles.
- [ ] **System hardening ("pull-the-plug" safety).** Read-only root via
      OverlayFS (`raspi-config`) plus a hardware watchdog
      (`dtparam=watchdog=on`) for auto-recovery, to protect SD cards and keep
      24/7 uptime.
- [ ] **Zero-copy rendering (`kmssink`).** Render directly to hardware display
      planes with `capture-io-mode=4` (DMABUF) for the lowest-latency,
      lowest-CPU display path.

---

## Sequencing

```
Now ─────────────────────────────────────────────────────────────▶ Later

sub-10ms campaign (ongoing, top priority)
A0 refactor ─┐
A1 spike ────┴─▶ A2 mac collaborator ─▶ A3 solo leader ─▶ A4 mixed ─▶ A5 HW decode ─▶ A6 wrapper
B0 overlay ─▶ B1 offline captions ─▶ B2 plugin host ─▶ B3 2nd plugin ─▶ B4 live captions
C: precision sync / OSC / hardening / kmssink (independent, Pi-only, any time)
```

A0 and B0 are the next concrete steps. Both are low-risk, Pi-beneficial, and
unblock everything downstream.

## Explicit non-goals

- A desktop app that owns UI or show state.
- A generic cross-platform clock/sync framework before two real
  implementations exist.
- Any platform or plugin feature that regresses Pi sync performance.
