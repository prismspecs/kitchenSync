"""MIDI management package for KitchenSync"""

from .manager import MidiManager, MidiError, MockMidiOut
from .scheduler import MidiScheduler

__all__ = ["MidiManager", "MidiScheduler", "MidiError", "MockMidiOut"]
