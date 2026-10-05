"""Offline timing contracts for explicit agent/tool fan-out groups."""
from .core import InputError, check
from .recorder import Recorder

__all__ = ["InputError", "Recorder", "check"]
__version__ = "0.1.0"
