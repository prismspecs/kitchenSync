"""Debug and overlay package for KitchenSync"""

from .html_overlay import HTMLDebugManager, HTMLDebugOverlay
from .simple_overlay import SimpleDebugManager, SimpleDebugOverlay

__all__ = [
    "HTMLDebugManager",
    "HTMLDebugOverlay",
    "SimpleDebugManager",
    "SimpleDebugOverlay",
]
