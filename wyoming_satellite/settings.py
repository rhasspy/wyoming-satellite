"""Satellite settings."""
from abc import ABC
from dataclasses import dataclass
from typing import List, Optional


@dataclass(frozen=True)
class ServiceSettings(ABC):
    uri: Optional[str] = None
    command: Optional[List[str]] = None
    reconnect_seconds: float = 3.0

    @property
    def enabled(self) -> bool:
        return bool(self.uri or self.command)


@dataclass(frozen=True)
class MicSettings(ServiceSettings):
    volume_multiplier: float = 1.0
    auto_gain: int = 0
    noise_suppression: int = 0
    rate: int = 16000
    width: int = 2
    channels: int = 1
    samples_per_chunk: int = 1024

    @property
    def needs_webrtc(self) -> bool:
        return self.enabled and ((self.auto_gain > 0) or (self.noise_suppression > 0))

    @property
    def needs_processing(self) -> bool:
        return self.enabled and ((self.volume_multiplier != 1.0) or self.needs_webrtc)


@dataclass(frozen=True)
class SndSettings(ServiceSettings):
    volume_multiplier: float = 1.0
    awake_wav: Optional[str] = None
    done_wav: Optional[str] = None
    rate: int = 22050
    width: int = 2
    channels: int = 1
    samples_per_chunk: int = 1024

    @property
    def needs_processing(self) -> bool:
        return self.enabled and (self.volume_multiplier != 1.0)


@dataclass(frozen=True)
class WakeSettings(ServiceSettings):
    names: Optional[List[str]] = None
    rate: int = 16000
    width: int = 2
    channels: int = 1


@dataclass(frozen=True)
class VadSettings:
    enabled: bool = False
    threshold: float = 0.5
    trigger_level: int = 1
    buffer_seconds: float = 2.0
    wake_word_timeout: Optional[float] = 5.0


@dataclass(frozen=True)
class EventSettings(ServiceSettings):
    startup: Optional[List[str]] = None
    streaming_start: Optional[List[str]] = None
    streaming_stop: Optional[List[str]] = None
    detect: Optional[List[str]] = None
    detection: Optional[List[str]] = None
    transcript: Optional[List[str]] = None
    stt_start: Optional[List[str]] = None
    stt_stop: Optional[List[str]] = None
    synthesize: Optional[List[str]] = None
    tts_start: Optional[List[str]] = None
    tts_stop: Optional[List[str]] = None
    error: Optional[List[str]] = None


@dataclass(frozen=True)
class SatelliteSettings:
    mic: MicSettings
    vad: VadSettings
    wake: WakeSettings
    snd: SndSettings
    event: EventSettings
    restart_timeout: float = 5.0
