"""Voice satellite using the Wyoming protocol."""
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
__version__ = (_DIR / "VERSION").read_text(encoding="utf-8").strip()

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
