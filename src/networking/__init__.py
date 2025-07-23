"""Networking package for KitchenSync"""

# Import from communication.py (preferred modern implementation)
from .communication import (
    SyncBroadcaster, SyncReceiver, CommandManager, CommandListener, NetworkError
)

# Import from manager.py (legacy implementation - for compatibility)
from .manager import (
    NetworkManager, LeaderNetworking, CollaboratorNetworking
)

# Export the modern communication classes as primary API
__all__ = [
    # Modern communication classes (preferred)
    'SyncBroadcaster', 
    'SyncReceiver', 
    'CommandManager', 
    'CommandListener', 
    'NetworkError',
    
    # Legacy manager classes (for backward compatibility)
    'NetworkManager',
    'LeaderNetworking', 
    'CollaboratorNetworking'
]
