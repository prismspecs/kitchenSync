#!/usr/bin/env python3
"""
Shared node helpers used by both leader.py and collaborator.py.

These lived as near-identical copies in both entry points; the copies drifted
(the leader once lacked the target-device filter the collaborator had, which
let a broadcast config update demote it to a collaborator). One home per fact.
"""

import os
import subprocess
import sys
import threading
import time
import traceback
from pathlib import Path
from typing import Optional

from core.logger import log_info, log_warning, log_error, log_file_paths


def install_startup_crash_logger(repo_dir: Path) -> None:
    """Log uncaught exceptions to logs/startup_crash.log — catches import-time
    errors that happen before normal logging is initialized."""

    def _hook(exc_type, exc_value, exc_tb):
        log_dir = repo_dir / "logs"
        log_dir.mkdir(exist_ok=True)
        with open(log_dir / "startup_crash.log", "a") as f:
            f.write(f"--- CRASH at {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
            traceback.print_exception(exc_type, exc_value, exc_tb, file=f)
        traceback.print_exception(exc_type, exc_value, exc_tb)

    sys.excepthook = _hook


def message_targets_this_device(msg: dict, device_id: str) -> bool:
    """True if a command with an optional target_device_id is meant for us.
    EVERY handler for device-addressed messages must apply this (see
    ksync-architecture-contract invariant 6)."""
    target_device_id = msg.get("target_device_id")
    return not target_device_id or target_device_id == device_id


def start_device_update(component: str) -> None:
    """git pull + reboot, in a background thread (the web-UI Update flow)."""
    log_info("Device update requested — git pull && reboot", component=component)

    def _do_update():
        repo = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        try:
            result = subprocess.run(
                ["git", "pull"],
                cwd=repo, capture_output=True, text=True, timeout=30,
            )
            log_info(f"Update git pull: {result.stdout.strip() or result.stderr.strip()}", component=component)
        except Exception as e:
            log_warning(f"Update git pull failed: {e}", component=component)

        time.sleep(2)
        reboot_commands = [
            ["sudo", "-n", "reboot"],
            ["sudo", "-n", "/sbin/reboot"],
            ["sudo", "-n", "/usr/sbin/reboot"],
            ["sudo", "-n", "systemctl", "reboot"],
        ]
        result = None
        for cmd in reboot_commands:
            result = subprocess.run(cmd, capture_output=True, text=True)
            log_info(
                f"Device update: {' '.join(cmd)} returned rc={result.returncode} — "
                f"{result.stderr.strip() or result.stdout.strip()}",
                component=component,
            )
            if result.returncode == 0:
                return
        log_error(
            f"Device update: all reboot attempts failed — last stderr: {result.stderr.strip() if result else 'n/a'}",
            component=component,
        )

    threading.Thread(target=_do_update, daemon=True).start()


def read_recent_log(max_lines: int = 100, max_chars: int = 30000, missing_note: str = "No log file found.") -> str:
    """Tail the system log for log_request replies, capped to avoid UDP
    datagram truncation (incident 1a57a01)."""
    try:
        sys_log_path = log_file_paths().get("system", "logs/kitchensync.log")
        if not os.path.exists(sys_log_path):
            return missing_note
        with open(sys_log_path, "r", errors="replace") as f:
            content = "".join(f.readlines()[-max_lines:])
        if len(content) > max_chars:
            content = "... [TRUNCATED] ...\n" + content[-max_chars:]
        return content
    except Exception as exc:
        return f"Error reading logs: {exc}"
