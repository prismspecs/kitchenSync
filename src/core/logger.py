#!/usr/bin/env python3
"""
Centralized lightweight logger for KitchenSync.
Writes to /tmp so it works under systemd or desktop sessions without extra setup.
"""

import os
import sys
import time
from typing import Dict, Optional


LOG_DIR = "/tmp"
SYSTEM_LOG_PATH = os.path.join(LOG_DIR, "kitchensync_system.log")


def _ensure_log_dir() -> None:
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
    except Exception:
        # /tmp should always exist; ignore failures
        pass


def _write(level: str, message: str, component: Optional[str] = None) -> None:
    _ensure_log_dir()
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    pid = os.getpid()
    if component is None:
        component = os.path.basename(sys.argv[0]) or "unknown"
    line = f"[{timestamp}] [{level}] [{component}] (pid={pid}) {message}\n"
    try:
        with open(SYSTEM_LOG_PATH, "a") as f:
            f.write(line)
    except Exception:
        # As a last resort, print
        try:
            print(line, end="")
        except Exception:
            pass


def log_debug(message: str, component: Optional[str] = None) -> None:
    _write("DEBUG", message, component)


def log_info(message: str, component: Optional[str] = None) -> None:
    _write("INFO", message, component)


def log_warning(message: str, component: Optional[str] = None) -> None:
    _write("WARN", message, component)


def log_error(message: str, component: Optional[str] = None) -> None:
    _write("ERROR", message, component)


def snapshot_env() -> Dict[str, str]:
    """Capture relevant environment variables for diagnostics and log them."""
    keys = [
        "DISPLAY",
        "XDG_SESSION_TYPE",
        "XDG_RUNTIME_DIR",
        "WAYLAND_DISPLAY",
        "XAUTHORITY",
    ]
    env = {k: os.environ.get(k, "") for k in keys}
    try:
        log_info(
            "Environment: "
            + ", ".join([f"{k}={v or 'unset'}" for k, v in env.items()]),
            component="env",
        )
    except Exception:
        pass
    return env


def log_file_paths() -> Dict[str, str]:
    """Return paths to system-wide logs for user convenience."""
    return {
        "system": SYSTEM_LOG_PATH,
        "vlc_main": os.path.join(LOG_DIR, "kitchensync_vlc.log"),
        "vlc_stdout": os.path.join(LOG_DIR, "kitchensync_vlc_stdout.log"),
        "vlc_stderr": os.path.join(LOG_DIR, "kitchensync_vlc_stderr.log"),
        "overlay_leader": os.path.join(LOG_DIR, "kitchensync_debug_leader-pi.txt"),
    }
