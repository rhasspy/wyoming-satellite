"""Voice activity detection."""
from typing import Optional
from .utils import AudioBuffer, chunk_samples


class SileroVad:
    """Voice activity detection with silero VAD."""

    def __init__(self, threshold: float, trigger_level: int) -> None:
        from pysilero_vad import SileroVoiceActivityDetector

        self.detector = SileroVoiceActivityDetector()
        self.threshold = threshold
        self.trigger_level = trigger_level
        self._activation = 0
        self._audio_buffer = AudioBuffer(self.detector.chunk_bytes())

    def __call__(self, audio_bytes: Optional[bytes]) -> bool:
        if audio_bytes is None:
            # Reset
            self._activation = 0
            self.detector.reset()
            return False

        for sub_chunk in chunk_samples(
            audio_bytes,
            self.detector.chunk_bytes(),
            self._audio_buffer
        ):
            if self.detector(sub_chunk) >= self.threshold:
                # Speech detected
                self._activation += 1
                if self._activation >= self.trigger_level:
                    self._activation = 0
                    return True
        else:
            # Silence detected
            self._activation = max(0, self._activation - 1)

        return False
