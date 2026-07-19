#!/usr/bin/env python3
"""
Captive portal + venue-WiFi provisioning for the kSync leader
(see docs/WIFI_PROVISIONING.md, Phases 2-3).

While the leader hosts the kSync hotspot, a dnsmasq drop-in resolves every
hostname to 10.42.0.1 and a NetworkManager dispatcher script redirects
port 80 to this server, so any phone that joins the hotspot lands on the
setup page automatically ("sign in to network" sheet).

On submit, the credentials are pushed to every collaborator over the
existing UDP control channel (`wifi_provision`), acks are collected, and
the whole cluster migrates together at `migrate_at`; the leader drops its
hotspot last. This is only safe because the hotspot is WPA2-encrypted.
"""

import json
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional
from urllib.parse import parse_qs, urlparse

from core.logger import log_info, log_warning
from networking.wifi_manager import (
    VENUE_CON_NAME,
    VENUE_PRIORITY,
    WifiManager,
    cluster_ssid,
    read_scan_cache,
)

PORTAL_PORT = 8081
# Seconds between credential submission and the coordinated network switch;
# the leader keeps re-sending the provision message during this window.
MIGRATE_DELAY_SECONDS = 20
PUSH_INTERVAL_SECONDS = 2.0
# Head start for collaborators at migrate_at, so the hotspot they are
# leaving doesn't vanish underneath their own switch.
MIGRATE_HEADSTART_SECONDS = 3.0

# Paths that OSes probe to detect a captive portal. Anything else
# unrecognized also redirects, but these must never 404.
CONNECTIVITY_CHECK_PATHS = {
    "/generate_204", "/gen_204",                      # Android
    "/hotspot-detect.html", "/library/test/success.html",  # Apple
    "/connecttest.txt", "/ncsi.txt", "/redirect",     # Windows
    "/canonical.html", "/success.txt",                # Firefox/misc
}


class WifiProvisioner:
    """Leader-side venue credential distribution and coordinated migration."""

    def __init__(self, config, command_manager, manager: Optional[WifiManager] = None):
        self.config = config
        self.command_manager = command_manager
        self.mgr = manager or WifiManager()
        self.state = "idle"  # idle | pushing | migrating | done | failed
        self.ssid = ""
        self._psk = ""
        self.token = ""
        self.migrate_at = 0.0
        self.acked: set = set()
        self._lock = threading.Lock()
        command_manager.register_handler("wifi_provision_ack", self._handle_ack)

    def _handle_ack(self, msg: dict, addr: tuple) -> None:
        device_id = msg.get("device_id")
        with self._lock:
            if device_id and msg.get("token") == self.token:
                if device_id not in self.acked:
                    log_info(f"WiFi: provision ack from {device_id}", component="wifi")
                self.acked.add(device_id)

    def status(self) -> dict:
        with self._lock:
            try:
                total = len(self.command_manager.collaborators)
            except Exception:
                total = 0
            return {
                "state": self.state,
                "ssid": self.ssid,
                "migrate_in": max(0, round(self.migrate_at - time.time())),
                "devices_total": total,
                "devices_acked": len(self.acked),
                "acked": sorted(self.acked),
            }

    def begin(self, ssid: str, psk: str) -> bool:
        """Start pushing credentials; returns False if a push is in flight."""
        with self._lock:
            if self.state in ("pushing", "migrating"):
                return False
            self.state = "pushing"
            self.ssid = ssid
            self._psk = psk
            self.token = uuid.uuid4().hex
            self.migrate_at = time.time() + MIGRATE_DELAY_SECONDS
            self.acked = set()
        threading.Thread(target=self._push_then_migrate, daemon=True).start()
        return True

    def _push_then_migrate(self) -> None:
        message = {
            "type": "wifi_provision",
            "ssid": self.ssid,
            "psk": self._psk,
            "token": self.token,
            "migrate_at": self.migrate_at,
        }
        log_info(f"WiFi: pushing venue credentials for '{self.ssid}' to cluster", component="wifi")
        while time.time() < self.migrate_at:
            try:
                self.command_manager.send_command(dict(message))
            except Exception as e:
                log_warning(f"WiFi: provision send failed: {e}", component="wifi")
            time.sleep(PUSH_INTERVAL_SECONDS)

        with self._lock:
            self.state = "migrating"
        time.sleep(MIGRATE_HEADSTART_SECONDS)
        self.mgr.stop_hotspot()
        if self.mgr.connect(self.ssid, self._psk, VENUE_CON_NAME, priority=VENUE_PRIORITY):
            with self._lock:
                self.state = "done"
            log_info(f"WiFi: leader migrated to '{self.ssid}'", component="wifi")
        else:
            log_warning(f"WiFi: leader could not join '{self.ssid}' - restoring hotspot", component="wifi")
            self.mgr.start_hotspot(cluster_ssid(self.config.cluster_name), self.config.hotspot_password)
            with self._lock:
                self.state = "failed"


PORTAL_PAGE = """<!DOCTYPE html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>kSync WiFi Setup</title>
<style>
body {{ font-family: -apple-system, system-ui, sans-serif; margin: 0; background: #111; color: #eee; }}
.wrap {{ max-width: 26rem; margin: 0 auto; padding: 1.5rem; }}
h1 {{ font-size: 1.3rem; }} h1 span {{ color: #6cf; }}
p, li {{ line-height: 1.45; color: #bbb; }}
label {{ display: block; margin: 1rem 0 0.3rem; }}
select, input {{ width: 100%; padding: 0.6rem; font-size: 1rem; border-radius: 6px;
  border: 1px solid #444; background: #1c1c1c; color: #eee; box-sizing: border-box; }}
button {{ width: 100%; margin-top: 1.2rem; padding: 0.8rem; font-size: 1.05rem;
  border: 0; border-radius: 6px; background: #2a7ae2; color: #fff; }}
.card {{ background: #1a1a1a; border: 1px solid #333; border-radius: 8px; padding: 1rem; margin-top: 1rem; }}
.ok {{ color: #6f6; }} .warn {{ color: #fc6; }}
</style></head>
<body><div class="wrap">
<h1><span>kSync</span> — cluster “{cluster}”</h1>
{body}
</div></body></html>
"""

FORM_BODY = """
<p>The installation is running on its own private network and needs no
setup. Connecting it to the venue WiFi is <b>optional</b> (for internet
access or control from your own network).</p>
<div class="card">
<form method="POST" action="/setup/wifi">
<label for="ssid">Venue WiFi network</label>
<select name="ssid" id="ssid">{options}</select>
<label for="ssid_manual">…or type the network name</label>
<input name="ssid_manual" id="ssid_manual" placeholder="(leave empty to use the list above)">
<label for="password">WiFi password</label>
<input type="password" name="password" id="password" autocomplete="off">
<button type="submit">Connect all {devices} device(s)</button>
</form>
</div>
<p class="warn">All kSync devices switch networks together about 20 seconds
after you submit. This setup network will disappear — if the screens keep
playing, it worked. If the venue WiFi doesn't work out, the kSync network
comes back by itself within a few minutes.</p>
"""

STATUS_BODY = """
<div class="card" id="status">Checking status…</div>
<p class="warn">Devices are switching to <b>{ssid}</b>. This setup network
will disappear during the switch. If the screens keep playing, everything
worked; if not, the kSync network returns within a few minutes and you can
try again.</p>
<script>
async function poll() {{
  try {{
    const r = await fetch('/api/wifi/status');
    const s = await r.json();
    let txt = '';
    if (s.state === 'pushing')
      txt = 'Sending WiFi details… <b>' + s.devices_acked + ' / ' + s.devices_total +
            '</b> devices confirmed. Switching in <b>' + s.migrate_in + 's</b>.';
    else if (s.state === 'migrating') txt = 'Switching networks now…';
    else if (s.state === 'done') txt = '<span class="ok">Done — all devices moved to ' + s.ssid + '.</span>';
    else if (s.state === 'failed') txt = '<span class="warn">Could not join ' + s.ssid +
            ' — the kSync network is coming back. Check the password and try again.</span>';
    else txt = 'Idle. <a href="/setup/wifi" style="color:#6cf">Back to setup</a>';
    document.getElementById('status').innerHTML = txt;
  }} catch (e) {{ /* network switch in progress — expected */ }}
  setTimeout(poll, 1500);
}}
poll();
</script>
"""


class CaptivePortalServer:
    """Small HTTP server for the setup page + captive-portal detection.

    Listens on PORTAL_PORT (a NetworkManager dispatcher script redirects the
    hotspot's port 80 here) and additionally binds port 80 directly when
    permitted, so the portal works even if the dispatcher isn't installed.
    """

    def __init__(self, config, provisioner: WifiProvisioner, port: int = PORTAL_PORT):
        self.config = config
        self.provisioner = provisioner
        self.port = port
        self._servers = []
        self._threads = []

    def _make_handler(self):
        portal = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _send(self, code: int, body: bytes, content_type: str = "text/html; charset=utf-8"):
                self.send_response(code)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

            def _redirect(self, location: str = "/setup/wifi"):
                self.send_response(302)
                self.send_header("Location", location)
                self.send_header("Content-Length", "0")
                self.end_headers()

            def do_GET(self):
                path = urlparse(self.path).path
                if path == "/setup/wifi":
                    self._send(200, portal.render_page().encode())
                elif path == "/api/wifi/status":
                    self._send(200, json.dumps(portal.provisioner.status()).encode(),
                               "application/json")
                else:
                    # Connectivity probes and everything else: redirect so
                    # the OS pops its "sign in to network" sheet.
                    self._redirect()

            def do_POST(self):
                path = urlparse(self.path).path
                if path != "/setup/wifi":
                    self._redirect()
                    return
                length = int(self.headers.get("Content-Length", 0) or 0)
                form = parse_qs(self.rfile.read(length).decode(errors="replace"))
                ssid = (form.get("ssid_manual", [""])[0] or form.get("ssid", [""])[0]).strip()
                password = form.get("password", [""])[0]
                if ssid:
                    portal.provisioner.begin(ssid, password)
                self._redirect()

        return Handler

    def render_page(self) -> str:
        state = self.provisioner.status()
        if state["state"] in ("pushing", "migrating", "done", "failed"):
            body = STATUS_BODY.format(ssid=_escape(state["ssid"]))
        else:
            options = "".join(
                f'<option value="{_escape(n["ssid"])}">{_escape(n["ssid"])} ({n.get("signal", "?")}%)</option>'
                for n in read_scan_cache()
            ) or '<option value="">(no networks found - type one below)</option>'
            body = FORM_BODY.format(options=options, devices=state["devices_total"] + 1)
        return PORTAL_PAGE.format(cluster=_escape(self.config.cluster_name), body=body)

    def start(self) -> None:
        handler = self._make_handler()
        ports = [self.port]
        if self.port != 80:
            ports.append(80)  # works when privileged; harmless to fail
        for port in ports:
            try:
                server = ThreadingHTTPServer(("", port), handler)
            except PermissionError:
                log_info(f"Portal: port {port} needs privileges - relying on the "
                         f"dispatcher redirect to {self.port}", component="wifi")
                continue
            except OSError as e:
                log_warning(f"Portal: could not bind port {port}: {e}", component="wifi")
                continue
            thread = threading.Thread(target=server.serve_forever, daemon=True,
                                      name=f"ksync-portal-{port}")
            thread.start()
            self._servers.append(server)
            self._threads.append(thread)
        if self._servers:
            bound = ", ".join(str(s.server_address[1]) for s in self._servers)
            log_info(f"Portal: WiFi setup page listening on port(s) {bound}", component="wifi")

    @property
    def bound_ports(self):
        return [s.server_address[1] for s in self._servers]

    def stop(self) -> None:
        for server in self._servers:
            try:
                server.shutdown()
                server.server_close()
            except Exception:
                pass
        self._servers = []
        self._threads = []


def _escape(text: str) -> str:
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))
