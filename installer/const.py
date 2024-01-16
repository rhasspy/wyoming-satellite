"""Constants and dataclasses."""
import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import List, Optional

from .dataclasses_json import DataClassJsonMixin

_DIR = Path(__file__).parent
_LOGGER = logging.getLogger()

PROGRAM_DIR = _DIR.parent
LOCAL_DIR = PROGRAM_DIR / "local"
SETTINGS_PATH = LOCAL_DIR / "settings.json"
SERVICES_DIR = LOCAL_DIR / "services"

RECORD_SECONDS = 5
RECORD_RMS_MIN = 30

TITLE = "Wyoming Satellite"
WIDTH = "75"
HEIGHT = "20"
LIST_HEIGHT = "12"


class SatelliteType(str, Enum):
    ALWAYS_STREAMING = "always"
    VAD = "vad"
    WAKE = "wake"


@dataclass
class SatelliteSettings(DataClassJsonMixin):
    name: str = "Wyoming Satellite"
    type: SatelliteType = SatelliteType.ALWAYS_STREAMING
    debug: bool = False
    event_service_command: Optional[List[str]] = None


@dataclass
class MicrophoneSettings(DataClassJsonMixin):
    device: Optional[str] = None
    noise_suppression: int = 0
    auto_gain: int = 0
    volume_multiplier: float = 1.0


@dataclass
class SpeakerSettings(DataClassJsonMixin):
    device: Optional[str] = None
    volume_multiplier: float = 1.0
    feedback_sounds: List[str] = field(default_factory=list)


@dataclass
class OpenWakeWordSettings(DataClassJsonMixin):
    wake_word: str = "ok_nabu"
    threshold: float = 0.5
    trigger_level: int = 1


@dataclass
class Porcupine1Settings(DataClassJsonMixin):
    wake_word: str = "porcupine"
    sensitivity: float = 0.5


@dataclass
class SnowboySettings(DataClassJsonMixin):
    wake_word: str = "snowboy"
    sensitivity: float = 0.5


class WakeWordSystem(str, Enum):
    OPENWAKEWORD = "openWakeWord"
    PORCUPINE1 = "porcupine1"
    SNOWBOY = "snowboy"


@dataclass
class WakeWordSettings(DataClassJsonMixin):
    system: Optional[WakeWordSystem] = None
    openwakeword: OpenWakeWordSettings = field(default_factory=OpenWakeWordSettings)
    porcupine1: Porcupine1Settings = field(default_factory=Porcupine1Settings)
    snowboy: SnowboySettings = field(default_factory=SnowboySettings)


@dataclass
class Settings(DataClassJsonMixin):
    satellite: SatelliteSettings = field(default_factory=SatelliteSettings)
    mic: MicrophoneSettings = field(default_factory=MicrophoneSettings)
    snd: SpeakerSettings = field(default_factory=SpeakerSettings)
    wake: WakeWordSettings = field(default_factory=WakeWordSettings)

    @staticmethod
    def load() -> "Settings":
        if SETTINGS_PATH.exists():
            _LOGGER.debug("Loading settings from %s", SETTINGS_PATH)
            with open(SETTINGS_PATH, "r", encoding="utf-8") as settings_file:
                settings_dict = json.load(settings_file)
                return Settings.from_dict(settings_dict)

        return Settings()

    def save(self) -> None:
        _LOGGER.debug("Saving settings to %s", SETTINGS_PATH)

        settings_dict = self.to_dict()
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)

        with open(SETTINGS_PATH, "w", encoding="utf-8") as settings_file:
            json.dump(settings_dict, settings_file, ensure_ascii=False, indent=2)
