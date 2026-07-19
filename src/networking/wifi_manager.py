#!/usr/bin/env python3
"""
WiFi Provisioning for kSync (see docs/WIFI_PROVISIONING.md)

Only the leader ever hosts an access point (kSync-<cluster_name>);
collaborators are seeded with a NetworkManager profile for that SSID so NM
itself keeps trying to join even after this process execv's into the role
process. Museum WiFi is optional — sync only needs the nodes to reach each
other.

Set KSYNC_NO_NETWORK_BOOTSTRAP=1 to skip all of this (dev machines).
"""

import json
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional

from core.logger import log_info, log_warning

# NetworkManager connection profile names owned by kSync.
HOTSPOT_CON_NAME = "ksync-hotspot"
CLUSTER_CON_NAME = "ksync-cluster"
VENUE_CON_NAME = "ksync-venue-wifi"

SSID_PREFIX = "kSync-"
NMCLI_TIMEOUT = 30
# Venue WiFi outranks the cluster profile so a provisioned node prefers the
# museum network; reverting just disables the venue profile again.
VENUE_PRIORITY = 100
# Scan results cached before the hotspot rises (brcmfmac can't reliably scan
# while hosting an AP); the captive portal reads this file.
SCAN_CACHE_PATH = Path(__file__).resolve().parents[2] / "logs" / "wifi_scan.json"
# Network watchdogs: how long a bad state must persist before reverting.
OFFLINE_GRACE_SECONDS = 180
WATCHDOG_INTERVAL_SECONDS = 30
# How long a collaborator blocks at boot waiting to join the cluster; the
# leader may be booting at the same time, so give its hotspot time to rise.
# After this, boot continues and NM keeps retrying in the background.
JOIN_WAIT_SECONDS = 60
# How long to wait for a saved profile to autoconnect before falling back.
AUTOCONNECT_WAIT_SECONDS = 30


def _split_terse(line: str) -> List[str]:
    """Split one line of `nmcli -t` output on unescaped colons."""
    fields = []
    current = []
    escaped = False
    for ch in line:
        if escaped:
            current.append(ch)
            escaped = False
        elif ch == "\\":
            escaped = True
        elif ch == ":":
            fields.append("".join(current))
            current = []
        else:
            current.append(ch)
    fields.append("".join(current))
    return fields


class WifiManager:
    """Thin wrapper around nmcli for status, scan, connect, and hotspot."""

    def __init__(self):
        self._wifi_device: Optional[str] = None

    def _run(self, args: List[str], timeout: int = NMCLI_TIMEOUT) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["nmcli"] + args, capture_output=True, text=True, timeout=timeout
        )

    def available(self) -> bool:
        """True if nmcli exists and NetworkManager is running."""
        if not shutil.which("nmcli"):
            return False
        try:
            return self._run(["general", "status"], timeout=10).returncode == 0
        except Exception:
            return False

    def _device_rows(self) -> List[List[str]]:
        try:
            result = self._run(["-t", "-f", "DEVICE,TYPE,STATE", "device"])
            if result.returncode != 0:
                return []
            return [_split_terse(l) for l in result.stdout.splitlines() if l]
        except Exception:
            return []

    def ethernet_connected(self) -> bool:
        for row in self._device_rows():
            if len(row) >= 3 and row[1] == "ethernet" and row[2] == "connected":
                return True
        return False

    def wifi_device(self) -> Optional[str]:
        if self._wifi_device:
            return self._wifi_device
        for row in self._device_rows():
            if len(row) >= 2 and row[1] == "wifi":
                self._wifi_device = row[0]
                return row[0]
        return None

    def wifi_connected_ssid(self) -> Optional[str]:
        """SSID of the current WiFi connection, or None. A running kSync
        hotspot does not count as being connected to WiFi."""
        try:
            result = self._run(["-t", "-f", "NAME,TYPE,DEVICE", "connection", "show", "--active"])
            if result.returncode != 0:
                return None
            for line in result.stdout.splitlines():
                row = _split_terse(line)
                if len(row) >= 2 and row[1] == "802-11-wireless" and row[0] != HOTSPOT_CON_NAME:
                    return row[0]
        except Exception:
            pass
        return None

    def hotspot_active(self) -> bool:
        try:
            result = self._run(["-t", "-f", "NAME", "connection", "show", "--active"])
            return result.returncode == 0 and HOTSPOT_CON_NAME in [
                _split_terse(l)[0] for l in result.stdout.splitlines() if l
            ]
        except Exception:
            return False

    def saved_wifi_profiles(self) -> List[str]:
        """Names of saved infrastructure WiFi profiles (excludes the hotspot)."""
        profiles = []
        try:
            result = self._run(["-t", "-f", "NAME,TYPE", "connection", "show"])
            if result.returncode != 0:
                return []
            for line in result.stdout.splitlines():
                row = _split_terse(line)
                if len(row) >= 2 and row[1] == "802-11-wireless" and row[0] != HOTSPOT_CON_NAME:
                    profiles.append(row[0])
        except Exception:
            pass
        return profiles

    def scan(self) -> List[Dict[str, str]]:
        """Visible networks as [{ssid, signal, security}], strongest first."""
        networks = []
        try:
            result = self._run(
                ["-t", "-f", "SSID,SIGNAL,SECURITY", "device", "wifi", "list", "--rescan", "yes"],
                timeout=45,
            )
            if result.returncode != 0:
                return []
            seen = set()
            for line in result.stdout.splitlines():
                row = _split_terse(line)
                if len(row) >= 3 and row[0] and row[0] not in seen:
                    seen.add(row[0])
                    networks.append({"ssid": row[0], "signal": row[1], "security": row[2]})
        except Exception:
            pass
        return networks

    def connect(self, ssid: str, psk: str, con_name: str = VENUE_CON_NAME,
                priority: int = VENUE_PRIORITY) -> bool:
        """Join a network now, saving it as an autoconnect profile."""
        self.ensure_profile(ssid, psk, con_name, priority=priority)
        try:
            result = self._run(["connection", "up", con_name], timeout=60)
            if result.returncode == 0:
                log_info(f"WiFi: connected to '{ssid}'", component="wifi")
                return True
            log_warning(f"WiFi: connect to '{ssid}' failed: {result.stderr.strip()}", component="wifi")
        except Exception as e:
            log_warning(f"WiFi: connect to '{ssid}' failed: {e}", component="wifi")
        return False

    def ensure_profile(self, ssid: str, psk: str, con_name: str, priority: int = 0) -> None:
        """Create or update a saved WPA2 profile that autoconnects forever.

        autoconnect-retries 0 = infinite: NetworkManager itself keeps trying
        to join whenever the SSID appears, so provisioning survives this
        process being replaced by the role process (os.execv) and reboots.
        """
        device = self.wifi_device() or "wlan0"
        settings = [
            "802-11-wireless.ssid", ssid,
            "wifi-sec.key-mgmt", "wpa-psk",
            "wifi-sec.psk", psk,
            "connection.autoconnect", "yes",
            "connection.autoconnect-retries", "0",
            "connection.autoconnect-priority", str(priority),
        ]
        try:
            existing = self._run(
                ["-t", "-f", "802-11-wireless.ssid", "connection", "show", con_name]
            )
            if existing.returncode == 0:
                self._run(["connection", "modify", con_name] + settings)
                return
            self._run(
                ["connection", "add", "type", "wifi", "ifname", device,
                 "con-name", con_name, "ssid", ssid]
                + settings[2:]  # ssid already given via the add positional
            )
        except Exception as e:
            log_warning(f"WiFi: could not save profile '{con_name}': {e}", component="wifi")

    def venue_active(self) -> bool:
        """True if the venue WiFi profile is the active connection."""
        try:
            result = self._run(["-t", "-f", "NAME", "connection", "show", "--active"])
            return result.returncode == 0 and VENUE_CON_NAME in [
                _split_terse(l)[0] for l in result.stdout.splitlines() if l
            ]
        except Exception:
            return False

    def revert_to_cluster(self, cluster_ssid_: str, cluster_psk: str) -> None:
        """Abandon the venue WiFi and fall back to the kSync cluster network.

        The cluster profile is (re)seeded BEFORE the venue profile is
        disabled so a node can never be left with no candidate network.
        """
        log_warning(f"WiFi: reverting to cluster network '{cluster_ssid_}'", component="wifi")
        self.ensure_profile(cluster_ssid_, cluster_psk, CLUSTER_CON_NAME)
        try:
            self._run(["connection", "modify", VENUE_CON_NAME, "connection.autoconnect", "no"])
            self._run(["connection", "down", VENUE_CON_NAME])
        except Exception as e:
            log_warning(f"WiFi: revert failed: {e}", component="wifi")

    def cache_scan(self) -> List[Dict[str, str]]:
        """Scan and persist results for the captive portal (which cannot
        rescan once the AP is up)."""
        networks = self.scan()
        try:
            SCAN_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
            SCAN_CACHE_PATH.write_text(
                json.dumps({"scanned_at": time.time(), "networks": networks})
            )
        except Exception as e:
            log_warning(f"WiFi: could not write scan cache: {e}", component="wifi")
        return networks

    def start_hotspot(self, ssid: str, psk: str) -> bool:
        """Host an access point (NM provides DHCP/NAT at 10.42.0.1).

        The profile is pinned to autoconnect=no so a stored hotspot can
        never outrank a real WiFi profile at boot — only kSync raises it.
        """
        device = self.wifi_device()
        if not device:
            log_warning("WiFi: no wifi device found, cannot start hotspot", component="wifi")
            return False
        if self.hotspot_active():
            return True
        try:
            result = self._run([
                "device", "wifi", "hotspot",
                "ifname", device,
                "con-name", HOTSPOT_CON_NAME,
                "ssid", ssid,
                "band", "bg",
                "password", psk,
            ], timeout=60)
            if result.returncode != 0:
                log_warning(f"WiFi: hotspot failed: {result.stderr.strip()}", component="wifi")
                return False
            self._run(["connection", "modify", HOTSPOT_CON_NAME, "connection.autoconnect", "no"])
            log_info(f"WiFi: hotspot '{ssid}' up at 10.42.0.1", component="wifi")
            return True
        except Exception as e:
            log_warning(f"WiFi: hotspot failed: {e}", component="wifi")
            return False

    def stop_hotspot(self) -> None:
        try:
            self._run(["connection", "down", HOTSPOT_CON_NAME])
        except Exception:
            pass


def cluster_ssid(cluster_name: str) -> str:
    return f"{SSID_PREFIX}{cluster_name}"


def ensure_network(config, manager: Optional[WifiManager] = None,
                   on_status: Optional[Callable[[str], None]] = None) -> str:
    """Boot-time network bootstrap. Returns the resulting state:

    "skipped"   - disabled via env, or nmcli/NetworkManager unavailable
    "ethernet"  - wired, nothing to do
    "wifi"      - joined an infrastructure network
    "hotspot"   - leader is hosting kSync-<cluster_name>
    "searching" - collaborator profile seeded; NM keeps trying in background
    "offline"   - no usable network interface

    Never raises: any failure degrades to a logged state so boot continues.
    """
    def status(msg: str) -> None:
        print(f" Network: {msg}")
        log_info(f"WiFi bootstrap: {msg}", component="wifi")
        if on_status:
            try:
                on_status(msg)
            except Exception:
                pass

    if os.environ.get("KSYNC_NO_NETWORK_BOOTSTRAP") == "1":
        return "skipped"

    mgr = manager or WifiManager()
    try:
        if not mgr.available():
            status("NetworkManager not available, skipping WiFi bootstrap")
            return "skipped"

        if mgr.ethernet_connected():
            status("ethernet connected")
            return "ethernet"

        if not mgr.wifi_device():
            status("no WiFi device and no ethernet - node is offline")
            return "offline"

        ssid = mgr.wifi_connected_ssid()
        if ssid:
            status(f"already connected to WiFi '{ssid}'")
            return "wifi"

        # Explicit venue credentials (USB ksync.ini) take precedence.
        venue_ssid = config.wifi_ssid
        if venue_ssid:
            status(f"joining configured WiFi '{venue_ssid}'...")
            if mgr.connect(venue_ssid, config.wifi_password):
                return "wifi"
            status(f"could not join '{venue_ssid}'")

        # Give any saved profile a chance to autoconnect.
        if mgr.saved_wifi_profiles():
            status("waiting for saved WiFi to connect...")
            deadline = time.monotonic() + AUTOCONNECT_WAIT_SECONDS
            while time.monotonic() < deadline:
                ssid = mgr.wifi_connected_ssid()
                if ssid:
                    status(f"connected to WiFi '{ssid}'")
                    return "wifi"
                time.sleep(2)

        # Self-hosted cluster network. Only the leader ever hosts an AP.
        ap_ssid = cluster_ssid(config.cluster_name)
        psk = config.hotspot_password

        if config.is_leader:
            # Scan while the radio is still free: the captive portal serves
            # this cached list because the AP can't rescan reliably.
            status("scanning nearby networks for the setup portal...")
            mgr.cache_scan()
            status(f"hosting setup network '{ap_ssid}' (password: {psk}, portal: http://10.42.0.1)")
            if mgr.start_hotspot(ap_ssid, psk):
                return "hotspot"
            return "offline"

        # Collaborator/bystander: seed the cluster profile so NetworkManager
        # keeps joining attempts alive after os.execv, then wait a bounded
        # time for the leader's hotspot (it may be booting right now too).
        status(f"looking for cluster network '{ap_ssid}'...")
        mgr.ensure_profile(ap_ssid, psk, CLUSTER_CON_NAME)
        deadline = time.monotonic() + JOIN_WAIT_SECONDS
        while time.monotonic() < deadline:
            ssid = mgr.wifi_connected_ssid()
            if ssid:
                status(f"joined '{ssid}'")
                return "wifi"
            time.sleep(3)
        status(f"'{ap_ssid}' not found yet - continuing boot, will keep trying")
        return "searching"
    except Exception as e:
        log_warning(f"WiFi bootstrap error: {e}", component="wifi")
        return "skipped"


def read_scan_cache() -> List[Dict[str, str]]:
    """Networks cached by cache_scan() before the hotspot went up."""
    try:
        data = json.loads(SCAN_CACHE_PATH.read_text())
        return data.get("networks", [])
    except Exception:
        return []


# Provision tokens already handled; the leader re-sends over UDP so
# duplicates are expected and must only be acked, not re-applied.
_seen_provision_tokens: set = set()


def handle_wifi_provision(msg: Dict, config, send_ack: Callable[[str], None],
                          manager: Optional[WifiManager] = None) -> bool:
    """Collaborator-side handler for a leader's `wifi_provision` message.

    Acks receipt, then applies the venue profile at `migrate_at` so the
    whole cluster switches networks together. Returns True if the migration
    was scheduled (or already was for this token).
    """
    ssid = msg.get("ssid")
    psk = msg.get("psk")
    token = msg.get("token")
    migrate_at = msg.get("migrate_at", 0)
    if not ssid or psk is None or not token:
        return False

    mgr = manager or WifiManager()
    if token in _seen_provision_tokens:
        # The leader may have missed the first ack (UDP) — always re-ack.
        try:
            send_ack(token)
        except Exception:
            pass
        return True

    if not mgr.available():
        log_warning("WiFi: provision received but NetworkManager unavailable", component="wifi")
        return False

    _seen_provision_tokens.add(token)
    try:
        send_ack(token)
    except Exception:
        pass

    delay = max(0.0, float(migrate_at) - time.time())
    log_info(f"WiFi: venue credentials received for '{ssid}', migrating in {delay:.0f}s", component="wifi")

    def apply():
        if not mgr.connect(ssid, psk, VENUE_CON_NAME, priority=VENUE_PRIORITY):
            # Failed join: watchdog/autoconnect will bring us back to the
            # cluster network, but don't leave a broken profile outranking it.
            mgr.revert_to_cluster(cluster_ssid(config.cluster_name), config.hotspot_password)

    threading.Timer(delay, apply).start()
    return True


def start_leader_network_watchdog(config, manager: Optional[WifiManager] = None,
                                  get_peer_silence: Optional[Callable[[], Optional[float]]] = None,
                                  interval: float = WATCHDOG_INTERVAL_SECONDS) -> threading.Thread:
    """Re-raise the leader's hotspot when the venue network stops working.

    Triggers when the leader is offline for OFFLINE_GRACE_SECONDS, or when
    it is on WiFi but every known collaborator has been silent that long —
    the signature of venue WiFi with AP client isolation, where the leader
    connects fine but sync can't reach anyone.

    get_peer_silence returns seconds since ANY collaborator was last heard,
    or None if none ever registered (single-node installs must not revert).
    """
    mgr = manager or WifiManager()

    def loop():
        offline_since = None
        while True:
            time.sleep(interval)
            try:
                if mgr.ethernet_connected() or mgr.hotspot_active():
                    offline_since = None
                    continue
                on_wifi = mgr.wifi_connected_ssid() is not None

                peers_silent = False
                if on_wifi and get_peer_silence:
                    silence = get_peer_silence()
                    peers_silent = silence is not None and silence >= OFFLINE_GRACE_SECONDS

                if on_wifi and not peers_silent:
                    offline_since = None
                    continue

                if not on_wifi:
                    now = time.monotonic()
                    if offline_since is None:
                        offline_since = now
                        continue
                    if now - offline_since < OFFLINE_GRACE_SECONDS:
                        continue

                ap_ssid = cluster_ssid(config.cluster_name)
                reason = "collaborators unreachable on venue WiFi" if peers_silent else "no network"
                log_warning(f"WiFi watchdog: {reason} - reverting to hotspot '{ap_ssid}'", component="wifi")
                if on_wifi:
                    mgr.revert_to_cluster(ap_ssid, config.hotspot_password)
                if mgr.start_hotspot(ap_ssid, config.hotspot_password):
                    offline_since = None
            except Exception as e:
                log_warning(f"WiFi watchdog error: {e}", component="wifi")

    thread = threading.Thread(target=loop, daemon=True, name="ksync-leader-net-watchdog")
    thread.start()
    return thread


def start_collaborator_network_watchdog(config, leader_contact_active: Callable[[], bool],
                                        manager: Optional[WifiManager] = None,
                                        interval: float = WATCHDOG_INTERVAL_SECONDS) -> threading.Thread:
    """Fall back to the cluster network when the venue WiFi hides the leader.

    Only acts while the venue profile is the active connection: on the
    cluster network (or none), NetworkManager's autoconnect already handles
    rejoining, and there is nothing safe to revert.
    """
    mgr = manager or WifiManager()

    def loop():
        silent_since = None
        while True:
            time.sleep(interval)
            try:
                if leader_contact_active() or not mgr.venue_active():
                    silent_since = None
                    continue
                now = time.monotonic()
                if silent_since is None:
                    silent_since = now
                    continue
                if now - silent_since >= OFFLINE_GRACE_SECONDS:
                    mgr.revert_to_cluster(cluster_ssid(config.cluster_name), config.hotspot_password)
                    silent_since = None
            except Exception as e:
                log_warning(f"WiFi watchdog error: {e}", component="wifi")

    thread = threading.Thread(target=loop, daemon=True, name="ksync-collab-net-watchdog")
    thread.start()
    return thread
