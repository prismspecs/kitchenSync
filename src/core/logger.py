#!/usr/bin/env python3
"""
Centralized lightweight logger for kSync.
Writes to /tmp so it works under systemd or desktop sessions without extra setup.
"""

import logging
import logging.handlers
import os
import sys
from typing import Dict, Optional

# Local logs directory
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LOG_DIR = os.path.join(BASE_DIR, "logs")
SYSTEM_LOG_PATH = os.path.join(LOG_DIR, "kitchensync.log")

# Global logging control
_ENABLE_SYSTEM_LOGGING = False

# Setup Python logging
_logger = logging.getLogger("kitchensync")
_logger.setLevel(logging.DEBUG)

def _setup_handlers():
    """Configure rotating file handler and console handler."""
    if not os.path.exists(LOG_DIR):
        try:
            os.makedirs(LOG_DIR, exist_ok=True)
        except Exception as e:
            print(f"Failed to create log directory: {e}", file=sys.stderr)
            return

    # Clear existing handlers to avoid duplicates on re-init
    _logger.handlers = []

    # Rotating File Handler: 1MB cap, 5 backups
    try:
        file_handler = logging.handlers.RotatingFileHandler(
            SYSTEM_LOG_PATH, maxBytes=1024 * 1024, backupCount=5
        )
        formatter = logging.Formatter(
            '[%(asctime)s] [%(levelname)s] [%(name)s] (pid=%(process)d) %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(formatter)
        _logger.addHandler(file_handler)
    except Exception as e:
        print(f"Failed to setup file logging: {e}", file=sys.stderr)

    # Console Handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    _logger.addHandler(console_handler)

# Initial setup
_setup_handlers()

def _should_log(level: int) -> bool:
    """Check if we should log based on current settings."""
    if level >= logging.WARNING:
        return True
    return _ENABLE_SYSTEM_LOGGING

def log_debug(message: str, component: Optional[str] = None) -> None:
    if _should_log(logging.DEBUG):
        _logger.debug(f"[{component or 'core'}] {message}")

def log_info(message: str, component: Optional[str] = None) -> None:
    if _should_log(logging.INFO):
        _logger.info(f"[{component or 'core'}] {message}")

def log_warning(message: str, component: Optional[str] = None) -> None:
    if _should_log(logging.WARNING):
        _logger.warning(f"[{component or 'core'}] {message}")

def log_error(message: str, component: Optional[str] = None) -> None:
    # Always log errors
    _logger.error(f"[{component or 'core'}] {message}")

def enable_system_logging(enabled: bool = True) -> None:
    """Enable or disable system logging globally."""
    global _ENABLE_SYSTEM_LOGGING
    _ENABLE_SYSTEM_LOGGING = enabled

def debug_log_info(message: str, component: str = "debug") -> None:
    log_info(message, component)

def debug_log_warning(message: str, component: str = "debug") -> None:
    log_warning(message, component)

def debug_log_error(message: str, component: str = "debug") -> None:
    log_error(message, component)

def snapshot_env() -> Dict[str, str]:
    """Capture relevant environment variables for diagnostics."""
    keys = ["DISPLAY", "XDG_SESSION_TYPE", "XDG_RUNTIME_DIR", "WAYLAND_DISPLAY"]
    env = {k: os.environ.get(k, "") for k in keys}
    log_info(f"Environment: {env}", component="env")
    return env

def log_file_paths() -> Dict[str, str]:
    """Return paths to logs for user convenience."""
    return {
        "system": SYSTEM_LOG_PATH,
        "logs_dir": LOG_DIR
    }
