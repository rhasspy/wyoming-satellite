"""Voice activity detection."""
import logging
from dataclasses import dataclass
from typing import Optional

_LOGGER = logging.getLogger(__name__)


class SileroVad:
    """Voice activity detection with silero VAD."""

    def __init__(self, threshold: float, trigger_level: int) -> None:
        from pysilero_vad import SileroVoiceActivityDetector

        self.detector = SileroVoiceActivityDetector()
        self.threshold = threshold
        self.trigger_level = trigger_level
        self._activation = 0

    def __call__(self, audio_bytes: Optional[bytes]) -> bool:
        if audio_bytes is None:
            # Reset
            self._activation = 0
            self.detector.reset()
            return False

        if self.detector(audio_bytes) >= self.threshold:
            # Speech detected
            self._activation += 1
            if self._activation >= self.trigger_level:
                self._activation = 0
                return True
        else:
            # Silence detected
            self._activation = max(0, self._activation - 1)

        return False


@dataclass
class VoiceCommandSegmenter:
    """Segments an audio stream into voice commands."""

    speech_seconds: float = 0.3
    """Seconds of speech before voice command has started."""

    silence_seconds: float = 1.0
    """Seconds of silence after voice command has ended."""

    timeout_seconds: float = 15.0
    """Maximum number of seconds before stopping with timeout=True."""

    reset_seconds: float = 1.0
    """Seconds before reset start/stop time counters."""

    in_command: bool = False
    """True if inside voice command."""

    _speech_seconds_left: float = 0.0
    """Seconds left before considering voice command as started."""

    _silence_seconds_left: float = 0.0
    """Seconds left before considering voice command as stopped."""

    _timeout_seconds_left: float = 0.0
    """Seconds left before considering voice command timed out."""

    _reset_seconds_left: float = 0.0
    """Seconds left before resetting start/stop time counters."""

    def __post_init__(self) -> None:
        """Reset after initialization."""
        self.reset()

    def reset(self) -> None:
        """Reset all counters and state."""
        self._speech_seconds_left = self.speech_seconds
        self._silence_seconds_left = self.silence_seconds
        self._timeout_seconds_left = self.timeout_seconds
        self._reset_seconds_left = self.reset_seconds
        self.in_command = False

    def process(self, chunk_seconds: float, is_speech: bool | None) -> bool:
        """Process samples using external VAD.

        Returns False when command is done.
        """
        self._timeout_seconds_left -= chunk_seconds
        if self._timeout_seconds_left <= 0:
            _LOGGER.warning(
                "VAD end of speech detection timed out after %s seconds",
                self.timeout_seconds,
            )
            self.reset()
            return False

        if not self.in_command:
            if is_speech:
                self._reset_seconds_left = self.reset_seconds
                self._speech_seconds_left -= chunk_seconds
                if self._speech_seconds_left <= 0:
                    # Inside voice command
                    self.in_command = True
                    self._silence_seconds_left = self.silence_seconds
                    _LOGGER.debug("Voice command started")
            else:
                # Reset if enough silence
                self._reset_seconds_left -= chunk_seconds
                if self._reset_seconds_left <= 0:
                    self._speech_seconds_left = self.speech_seconds
                    self._reset_seconds_left = self.reset_seconds
        elif not is_speech:
            # Silence in command
            self._reset_seconds_left = self.reset_seconds
            self._silence_seconds_left -= chunk_seconds
            if self._silence_seconds_left <= 0:
                # Command finished successfully
                self.reset()
                _LOGGER.debug("Voice command finished")
                return False
        else:
            # Speech in command.
            # Reset silence counter if enough speech.
            self._reset_seconds_left -= chunk_seconds
            if self._reset_seconds_left <= 0:
                self._silence_seconds_left = self.silence_seconds
                self._reset_seconds_left = self.reset_seconds

        return True
