"""Satellite settings."""
from abc import ABC
from dataclasses import dataclass
from typing import List, Optional


@dataclass(frozen=True)
class ServiceSettings(ABC):
    """Base class for service settings."""

    uri: Optional[str] = None
    """tcp://ip-address:port"""

    command: Optional[List[str]] = None
    """program + args"""

    reconnect_seconds: float = 3.0
    """Seconds before reconnection attempt is made."""

    @property
    def enabled(self) -> bool:
        """True if service is enabled."""
        return bool(self.uri or self.command)


@dataclass(frozen=True)
class MicSettings(ServiceSettings):
    """Microphone service settings."""

    volume_multiplier: float = 1.0
    """Multiplier for raw audio data (1.0 = no change)"""

    auto_gain: int = 0
    """Automatic gain control (0-31 dbFS)"""

    noise_suppression: int = 0
    """Level of noise suppression (0-4, 4 is max)"""

    rate: int = 16000
    """Sample rate of mic audio (hertz)"""

    width: int = 2
    """Sample width of mic audio (bytes)"""

    channels: int = 1
    """Sample channels in mic audio"""

    samples_per_chunk: int = 1024
    """Samples to read at a time from mic command"""

    @property
    def needs_webrtc(self) -> bool:
        """True if webrtc audio enhancements are needed."""
        return self.enabled and ((self.auto_gain > 0) or (self.noise_suppression > 0))

    @property
    def needs_processing(self) -> bool:
        """True if some audio pre-processing is needed for mic audio."""
        return self.enabled and ((self.volume_multiplier != 1.0) or self.needs_webrtc)


@dataclass(frozen=True)
class SndSettings(ServiceSettings):
    """Sound output service settings."""

    volume_multiplier: float = 1.0
    """Multiplier for raw audio data (1.0 = no change)"""

    awake_wav: Optional[str] = None
    """Path to WAV file played after wake word detection."""

    done_wav: Optional[str] = None
    """Path to WAV file played after voice command is recognized."""

    rate: int = 22050
    """Sample rate of output audio (hertz)"""

    width: int = 2
    """Sample width of output audio (bytes)"""

    channels: int = 1
    """Sample channels in output audio"""

    samples_per_chunk: int = 1024
    """Samples to write at a time to snd command"""

    disconnect_after_stop: bool = True
    """True if snd service should be disconnected after AudioStop."""

    @property
    def needs_processing(self) -> bool:
        """True if some pre-processing is needed for output audio."""
        return self.enabled and (self.volume_multiplier != 1.0)


@dataclass(frozen=True)
class WakeSettings(ServiceSettings):
    """Wake word service settings."""

    names: Optional[List[str]] = None
    """List of wake word names to listen for."""

    rate: int = 16000
    """Sample rate of wake word audio (hertz)"""

    width: int = 2
    """Sample width of wake word audio (bytes)"""

    channels: int = 1
    """Sample channels in wake word audio"""


@dataclass(frozen=True)
class VadSettings:
    """Voice activity detector settings."""

    enabled: bool = False
    """True if VAD should be used."""

    threshold: float = 0.5
    """Silence threshold (0-1, 1 is speech)"""

    trigger_level: int = 1
    """Number of chunks to cross threshold before activation."""

    buffer_seconds: float = 2.0
    """Seconds of audio before activation to keep/stream"""

    wake_word_timeout: Optional[float] = 5.0
    """Seconds before going back to sleep if wake word is not detected."""

    command_timeout: Optional[float] = 1.0
    """Seconds before stopping stream tranfer."""


@dataclass(frozen=True)
class EventSettings(ServiceSettings):
    """External event service settings."""

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
    """Wyoming satellite settings."""

    mic: MicSettings
    vad: VadSettings
    wake: WakeSettings
    snd: SndSettings
    event: EventSettings
    restart_timeout: float = 5.0
