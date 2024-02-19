"""Shared code for Wyoming satellite tests."""
import asyncio
import io
from collections.abc import Iterable
from typing import Optional

from wyoming.audio import AudioChunk, AudioStart, AudioStop
from wyoming.client import AsyncClient
from wyoming.event import Event

AUDIO_START = AudioStart(rate=16000, width=2, channels=1)
AUDIO_STOP = AudioStop()

AUDIO_CHUNK = AudioChunk(
    rate=16000, width=2, channels=1, audio=bytes([255] * 960)  # 30ms
)


class FakeStreamReaderWriter:
    def __init__(self) -> None:
        self._undrained_data = bytes()
        self._value = bytes()
        self._data_ready = asyncio.Event()

    def write(self, data: bytes) -> None:
        self._undrained_data += data

    def writelines(self, data: Iterable[bytes]) -> None:
        for line in data:
            self.write(line)

    async def drain(self) -> None:
        self._value += self._undrained_data
        self._undrained_data = bytes()
        self._data_ready.set()
        self._data_ready.clear()

    async def readline(self) -> bytes:
        while b"\n" not in self._value:
            await self._data_ready.wait()

        with io.BytesIO(self._value) as value_io:
            data = value_io.readline()
            self._value = self._value[len(data) :]
            return data

    async def readexactly(self, n: int) -> bytes:
        while len(self._value) < n:
            await self._data_ready.wait()

        data = self._value[:n]
        self._value = self._value[n:]
        return data


class MicClient(AsyncClient):
    async def read_event(self) -> Optional[Event]:
        # Send 30ms of audio every 30ms
        await asyncio.sleep(AUDIO_CHUNK.seconds)
        return AUDIO_CHUNK.event()

    async def write_event(self, event: Event) -> None:
        # Output only
        pass
