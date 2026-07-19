# WiFi Provisioning Design

How kSync devices get on a network in venues with no technical staff, no
ethernet, and any number of nodes (e.g. a 10-channel installation).

> **Status (2026-07-19):** Phases 1-3 implemented
> (`src/networking/wifi_manager.py`, `src/networking/captive_portal.py`,
> integrations in `kitchensync.py` / `leader.py` / `collaborator.py`,
> portal plumbing in `setup.sh`) and Phase 4 (docs) done. Verified by unit
> tests; AP mode and the captive-portal flow still need the real-hardware
> pass in `TESTING.md` §7.

## The core decision: museum WiFi is optional, not required

kSync nodes carry their video locally (USB/SD) and only exchange small UDP
sync/control packets — they need to talk to *each other*, not to the
internet. Joining museum/guest WiFi is actively risky for sync: those
networks commonly enable AP client isolation (devices can't see each other)
and block UDP broadcast/multicast, which the sync protocol depends on.

So the design is three connection tiers:

1. **Ethernet** (best): plug into a switch, nothing to configure.
2. **kSync private network** (wireless default): the leader hosts its own
   WiFi access point; collaborators find and join it automatically. Zero
   human interaction — the installation syncs by itself.
3. **Museum WiFi** (opt-in): staff join the leader's AP with a phone, a
   captive portal collects the credentials once, and the leader distributes
   them to every collaborator before the whole cluster migrates together.

Only the leader ever broadcasts an AP. That is what prevents the
"10 unprovisioned devices = 10 setup networks" problem: collaborators never
ask a human for credentials — they ask the leader.

The one-line pitch: *"Plug everything in. It syncs by itself. If you want it
on your WiFi, join the kSync network with your phone and type the password
once."*

---

## Phase 1 — Self-hosted network (zero-config wireless)

### New module: `src/networking/wifi_manager.py`

A thin wrapper around `nmcli` (NetworkManager is the Raspberry Pi OS
Bookworm default — no hostapd/dnsmasq to install or manage):

- `network_status()` — ethernet carrier? wifi connected? which SSID?
- `scan()` — scan results (SSID, signal, security), cached
- `connect(ssid, psk)`, `saved_profiles()`, `forget(ssid)`
- `start_hotspot(ssid, psk)` / `stop_hotspot()` — `nmcli device wifi
  hotspot` provides AP mode + DHCP + NAT at `10.42.0.1` in one call
- The hotspot profile is created with `autoconnect no`: only kSync code
  raises it, so it can never fight a real WiFi profile at boot.

Plus `ensure_network(config)` — the bootstrap state machine called from
`kitchensync.py` before the role process starts:

1. Ethernet carrier up → done (unchanged behavior).
2. A saved WiFi profile connects within ~30 s → done.
3. `wifi_ssid` / `wifi_password` present in the USB `ksync.ini` → save the
   profile and connect (power-user/bulk provisioning path — kept).
4. Otherwise, by role:
   - **Leader**: start hotspot `kSync-<cluster_name>` (WPA2, PSK from
     `hotspot_password`).
   - **Collaborator**: scan loop — join the SSID exactly matching
     `kSync-<cluster_name>`; retry forever (the leader may boot later).
   - **Bystander**: same as collaborator (it still needs the network to be
     provisioned later).

Bootstrap never blocks the show indefinitely: after a bounded wait the role
process starts regardless, and the scan/join loop continues in the
background — ethernet-plugged or already-provisioned setups see zero change.

### Config keys (`[KITCHENSYNC]`)

| key | default | meaning |
|---|---|---|
| `cluster_name` | `ksync` | Suffix of the hotspot SSID `kSync-<cluster_name>`. Lets two installations coexist in one building — collaborators only join their own cluster's SSID. |
| `hotspot_password` | `kitchensync` | WPA2 PSK of the leader hotspot. Must never be empty (credentials later transit this network). |
| `wifi_ssid` | *(empty)* | Optional venue WiFi to join (USB bulk-provisioning path). |
| `wifi_password` | *(empty)* | Password for `wifi_ssid`. |

### Use the screens

Every node drives a display, so the bootstrap states render on the output
itself and the projections become the setup instructions:

- Leader: `Setup network: kSync-gallery · password: kitchensync · open http://10.42.0.1`
- Collaborator: `Looking for kSync network "kSync-gallery"…`

### `setup.sh` prerequisites

- Add the service user to `netdev` (unprivileged `nmcli`).
- `rfkill unblock wifi`.
- Ensure the WiFi country / regulatory domain is set
  (`raspi-config nonint do_wifi_country`) — **AP mode silently fails on an
  unset regdomain**, which otherwise only shows up on a fresh SD card in
  the field.

---

## Phase 2 — Captive portal on the leader

- `/setup/wifi` page on the existing HTTP server
  (`src/remote/controller.py`): dropdown of scanned SSIDs + password field
  + explanation of the "keep private network" default.
- Captive-portal detection: `address=/#/10.42.0.1` drop-in at
  `/etc/NetworkManager/dnsmasq-shared.d/ksync.conf` (installed by
  `setup.sh`) resolves all DNS on the hotspot to the leader; answer the OS
  connectivity-check paths (`/generate_204`, `/hotspot-detect.html`,
  `/connecttest.txt`) with a redirect to `/setup/wifi` so phones pop the
  "sign in to network" sheet automatically.
- Single-radio gotcha: brcmfmac can't reliably scan while hosting an AP.
  Scan and cache **before** raising the hotspot; serve the cached list, and
  provide a manual-SSID text field as fallback.

## Phase 3 — Credential push + coordinated migration

Two new message types on the existing UDP control channel (port 5006):

- Leader → collaborators:
  `{"type": "wifi_provision", "ssid": …, "psk": …, "migrate_at": <unix ts ~20 s out>}`
  via `CommandManager.send_command` (already does per-node unicast +
  broadcast fallback).
- Collaborator → leader: `{"type": "wifi_provision_ack", "device_id": …}`.

Flow: portal submit → leader sends `wifi_provision`, collects acks against
its registered-collaborator list, portal shows "9/9 devices received" → at
`migrate_at` every node saves a NetworkManager profile (autoconnect yes,
priority 100) and connects; the leader drops its hotspot **last**.

Sending the PSK in cleartext is acceptable only because the hotspot is
WPA2-encrypted — never implement this over an open AP.

**Fallback watchdog (the un-brickable guarantee):**

- Collaborator: WiFi associated but no sync packets for ~3 min
  (`SyncReceiver.last_sync_time` already tracks this), or cannot associate
  at all → return to the Phase-1 scan loop.
- Leader: configured WiFi unreachable for ~3 min → re-raise the hotspot.

Wrong password, renamed network, dead router — every failure converges back
to the private-network state that always works.

## Phase 4 — Documentation

- README + `docs/INSTALLATION.md`: describe the three connection tiers.
- Bless a travel router (GL.iNet-class, ~$30) for large rooms / thick
  walls: to the code it is just another "known WiFi", zero special
  handling, and it adds ethernet ports.
- Honest Pi-radio limits: 2.4 GHz AP, ~10 clients is fine for sync traffic
  (video is local), but range through gallery walls is the real constraint.

---

## Non-goals / notes

- **No NTP/internet dependency**: sync is relative (leader clock over UDP);
  the private network needs no upstream. `ntp_check` treats "no internet"
  as normal in hotspot mode, not an error.
- **No collaborator APs, no AP election**: the leader role (already
  determined by USB config) is the only AP host.
- Hardware test checklist (see `docs/TESTING.md`): wrong-password recovery,
  and two clusters in one room with distinct `cluster_name`s.
