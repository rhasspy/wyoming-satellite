"""Voice satellite using the Wyoming protocol."""
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

__all__ = [
    "AlwaysStreamingSatellite",
    "EventSettings",
    "MicSettings",
    "SatelliteBase",
    "SatelliteSettings",
    "SndSettings",
    "VadSettings",
    "VadStreamingSatellite",
    "WakeSettings",
    "WakeStreamingSatellite",
]
