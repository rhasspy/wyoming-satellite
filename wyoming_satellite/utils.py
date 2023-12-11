"""Utilities for Wyoming satellite."""
import array
import asyncio
import logging
import wave
from pathlib import Path
from typing import Iterable, Iterator, List, Optional, Union

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


async def run_event_command(
    command: Optional[List[str]], command_input: Optional[str] = None
) -> None:
    """Run a custom event command with optional input."""
    if not command:
        return

    _LOGGER.debug("Running %s", command)
    program, *program_args = command
    proc = await asyncio.create_subprocess_exec(
        program, *program_args, stdin=asyncio.subprocess.PIPE
    )
    assert proc.stdin is not None

    if command_input:
        await proc.communicate(input=command_input.encode("utf-8"))
    else:
        proc.stdin.close()
        await proc.wait()


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
