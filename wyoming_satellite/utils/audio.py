"""Audio utilities."""
import array
import logging
import time
import wave
from pathlib import Path
from typing import Iterable, Iterator, Optional, Union

from pyring_buffer import RingBuffer
from wyoming.audio import AudioChunk, AudioStart, AudioStop
from wyoming.event import Event

_LOGGER = logging.getLogger()


class AudioBuffer:
    """Fixed-sized audio buffer with variable internal length."""

    def __init__(self, maxlen: int) -> None:
        """Initialize buffer."""
        self._buffer = bytearray(maxlen)
        self._length = 0

    @property
    def length(self) -> int:
        """Get number of bytes currently in the buffer."""
        return self._length

    def clear(self) -> None:
        """Clear the buffer."""
        self._length = 0

    def append(self, data: bytes) -> None:
        """Append bytes to the buffer, increasing the internal length."""
        data_len = len(data)
        if (self._length + data_len) > len(self._buffer):
            raise ValueError("Length cannot be greater than buffer size")

        self._buffer[self._length : self._length + data_len] = data
        self._length += data_len

    def to_bytes(self) -> bytes:
        """Convert written portion of buffer to bytes."""
        return bytes(self._buffer[: self._length])

    def __len__(self) -> int:
        """Get the number of bytes currently in the buffer."""
        return self._length

    def __bool__(self) -> bool:
        """Return True if there are bytes in the buffer."""
        return self._length > 0


def multiply_volume(chunk: bytes, volume_multiplier: float) -> bytes:
    """Multiplies 16-bit PCM samples by a constant."""

    def _clamp(val: float) -> float:
        """Clamp to signed 16-bit."""
        return max(-32768, min(32767, val))

    return array.array(
        "h",
        (int(_clamp(value * volume_multiplier)) for value in array.array("h", chunk)),
    ).tobytes()


def chunk_samples(
    samples: bytes,
    bytes_per_chunk: int,
    leftover_chunk_buffer: AudioBuffer,
) -> Iterable[bytes]:
    """Yield fixed-sized chunks from samples, keeping leftover bytes from previous call(s)."""

    if (len(leftover_chunk_buffer) + len(samples)) < bytes_per_chunk:
        # Extend leftover chunk, but not enough samples to complete it
        leftover_chunk_buffer.append(samples)
        return

    next_chunk_idx = 0

    if leftover_chunk_buffer:
        # Add to leftover chunk from previous call(s).
        bytes_to_copy = bytes_per_chunk - len(leftover_chunk_buffer)
        leftover_chunk_buffer.append(samples[:bytes_to_copy])
        next_chunk_idx = bytes_to_copy

        # Process full chunk in buffer
        yield leftover_chunk_buffer.to_bytes()
        leftover_chunk_buffer.clear()

    while next_chunk_idx < len(samples) - bytes_per_chunk + 1:
        # Process full chunk
        yield samples[next_chunk_idx : next_chunk_idx + bytes_per_chunk]
        next_chunk_idx += bytes_per_chunk

    # Capture leftover chunks
    if rest_samples := samples[next_chunk_idx:]:
        leftover_chunk_buffer.append(rest_samples)


def wav_to_events(
    wav_path: Union[str, Path],
    samples_per_chunk: int = 1024,
    volume_multiplier: float = 1.0,
) -> Iterator[Event]:
    """Load WAV audio for playback on an event (wake/done)."""
    with wave.open(str(wav_path), "rb") as wav_file:
        rate = wav_file.getframerate()
        width = wav_file.getsampwidth()
        channels = wav_file.getnchannels()

        timestamp = 0
        yield AudioStart(
            rate=rate, width=width, channels=channels, timestamp=timestamp
        ).event()

        audio_bytes = wav_file.readframes(samples_per_chunk)
        while audio_bytes:
            if volume_multiplier != 1.0:
                audio_bytes = multiply_volume(audio_bytes, volume_multiplier)

            chunk = AudioChunk(
                rate=rate,
                width=width,
                channels=channels,
                audio=audio_bytes,
                timestamp=timestamp,
            )
            yield chunk.event()
            timestamp += int(chunk.seconds * 1000)
            audio_bytes = wav_file.readframes(samples_per_chunk)

        yield AudioStop(timestamp=timestamp).event()


class DebugAudioWriter:
    def __init__(
        self,
        dir_path: Union[str, Path],
        suffix: str,
        rate: int = 16000,
        width: int = 2,
        channels: int = 1,
        ring_buffer_size: Optional[int] = None,
    ) -> None:
        self.dir_path = Path(dir_path)
        self.suffix = suffix
        self.rate = rate
        self.width = width
        self.channels = channels

        self._wav_path: Optional[Path] = None
        self._wav_writer: Optional[wave.Wave_write] = None

        # If ring buffer size is set, we will hold audio in a ring buffer
        # instead of directly writing it to disk.
        #
        # This allows only the last few seconds of wake word audio to be stored.
        self._ring_buffer: Optional[RingBuffer] = None
        if ring_buffer_size is not None:
            # Hold audio in a ring buffer before writing
            self._ring_buffer = RingBuffer(ring_buffer_size)

    def start(self, timestamp: Optional[int] = None) -> None:
        self.stop()

        if timestamp is None:
            timestamp = time.monotonic_ns()

        self._wav_path = self.dir_path / f"{timestamp}-{self.suffix}.wav"
        self._wav_path.parent.mkdir(parents=True, exist_ok=True)

        self._wav_writer = wave.open(str(self._wav_path), "wb")
        self._wav_writer.setframerate(self.rate)
        self._wav_writer.setsampwidth(self.width)
        self._wav_writer.setnchannels(self.channels)

        _LOGGER.debug("Started recording to %s", self._wav_path)

    def write(self, audio: bytes) -> None:
        if self._wav_writer is None:
            return

        if self._ring_buffer is not None:
            # Hold audio in a ring buffer before writing
            self._ring_buffer.put(audio)
        else:
            # Write directly to disk
            self._wav_writer.writeframes(audio)

    def stop(self) -> None:
        if self._wav_writer is None:
            return

        if self._ring_buffer is not None:
            # Write all audio now and reset buffer
            self._wav_writer.writeframes(self._ring_buffer.getvalue())
            self._ring_buffer = RingBuffer(self._ring_buffer.maxlen)

        self._wav_writer.close()
        self._wav_writer = None

        _LOGGER.debug("Stopped recording to %s", self._wav_path)
        self._wav_path = None
