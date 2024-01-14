"""Constants and dataclasses."""
import logging
import json
from enum import Enum
from dataclasses import dataclass, fields, asdict, field
from typing import Any, Dict, Optional, List
from pathlib import Path

_DIR = Path(__file__).parent
_LOGGER = logging.getLogger()

PROGRAM_DIR = _DIR.parent
LOCAL_DIR = PROGRAM_DIR / "local"
SETTINGS_PATH = LOCAL_DIR / "settings.json"
SERVICES_DIR = LOCAL_DIR / "services"

RECORD_SECONDS = 8
RECORD_RMS_MIN = 30

TITLE = "Wyoming Satellite"
WIDTH = "75"
HEIGHT = "20"
LIST_HEIGHT = "12"


class SatelliteType(str, Enum):
    ALWAYS_STREAMING = "always"
    VAD = "vad"
    WAKE = "wake"


class WakeWordSystem(str, Enum):
    OPENWAKEWORD = "openWakeWord"
    PORCUPINE1 = "porcupine1"
    SNOWBOY = "snowboy"


@dataclass
class Settings:
    microphone_device: Optional[str] = None
    noise_suppression_level: int = 0
    auto_gain: int = 0
    mic_volume_multiplier: float = 1.0

    sound_device: Optional[str] = None
    feedback_sounds: List[str] = field(default_factory=list)

    wake_word_system: Optional[WakeWordSystem] = None
    wake_word: Dict[WakeWordSystem, str] = field(
        default_factory=lambda: {
            WakeWordSystem.OPENWAKEWORD: "ok_nabu",
            WakeWordSystem.PORCUPINE1: "porcupine",
            WakeWordSystem.SNOWBOY: "snowboy",
        }
    )

    satellite_name: str = "Wyoming Satellite"
    satellite_type: SatelliteType = SatelliteType.ALWAYS_STREAMING

    debug_enabled: bool = False

    @staticmethod
    def load() -> "Settings":
        kwargs: Dict[str, Any] = {}

        if SETTINGS_PATH.exists():
            _LOGGER.debug("Loading settings from %s", SETTINGS_PATH)
            with open(SETTINGS_PATH, "r", encoding="utf-8") as settings_file:
                settings_dict = json.load(settings_file)

            for settings_field in fields(Settings):
                value = settings_dict.get(settings_field.name)
                if value is not None:
                    kwargs[settings_field.name] = value

        return Settings(**kwargs)

    def save(self) -> None:
        _LOGGER.debug("Saving settings to %s", SETTINGS_PATH)

        settings_dict = asdict(self)
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)

        with open(SETTINGS_PATH, "w", encoding="utf-8") as settings_file:
            json.dump(settings_dict, settings_file, ensure_ascii=False, indent=2)
