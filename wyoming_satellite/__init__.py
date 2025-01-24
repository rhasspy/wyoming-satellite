"""Voice satellite using the Wyoming protocol."""

import importlib.metadata
from pathlib import Path

from .satellite import (
    AlwaysStreamingSatellite,
    SatelliteBase,
    VadStreamingSatellite,
    WakeStreamingSatellite,
)
from .settings import (
    EventSettings,
    MicSettings,
    SatelliteSettings,
    SndSettings,
    VadSettings,
    WakeSettings,
)

_DIR = Path(__file__).parent
__version__ = importlib.metadata.version("wyoming-satellite")

__all__ = [
    "__version__",
    "AlwaysStreamingSatellite",
    "EventSettings",
    "MicSettings",
    "SatelliteBase",
    "SatelliteSettings",
    "SndSettings",
    "VadSettings",
    "VadStreamingSatellite",
    "WakeStreamingSatellite",
    "WakeSettings",
]
