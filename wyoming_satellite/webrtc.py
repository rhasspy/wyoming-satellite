"""webrtc audio processing."""
from typing import Final

from .utils import AudioBuffer, chunk_samples


class WebRtcAudio:
    """Audio processing using webrtc."""

    _sub_chunk_samples: Final = 160  # 10ms @ 16Khz
    _sub_chunk_bytes: Final = _sub_chunk_samples * 2  # 16-bit

    def __init__(self, auto_gain: int, noise_suppression: int) -> None:
        from webrtc_noise_gain import AudioProcessor

        self.audio_processor = AudioProcessor(auto_gain, noise_suppression)
        self.audio_buffer = AudioBuffer(self._sub_chunk_bytes)

    def __call__(self, audio_bytes: bytes) -> bytes:
        """Process in 10ms chunks."""
        clean_chunk = bytes()
        for sub_chunk in chunk_samples(
            audio_bytes, self._sub_chunk_bytes, self.audio_buffer
        ):
            result = self.audio_processor.Process10ms(sub_chunk)
            clean_chunk += result.audio

        return clean_chunk
