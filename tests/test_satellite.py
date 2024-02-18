import asyncio
import io
import logging
from collections.abc import Iterable
from pathlib import Path
from typing import Final, Optional
from unittest.mock import patch

import pytest
from wyoming.asr import Transcript
from wyoming.audio import AudioChunk
from wyoming.client import AsyncClient
from wyoming.event import Event, async_read_event
from wyoming.pipeline import PipelineStage, RunPipeline
from wyoming.satellite import RunSatellite, StreamingStarted, StreamingStopped
from wyoming.wake import Detection

from wyoming_satellite import (
    EventSettings,
    MicSettings,
    SatelliteSettings,
    WakeSettings,
    WakeStreamingSatellite,
)

from .shared import AUDIO_CHUNK

_LOGGER = logging.getLogger()

TIMEOUT: Final = 1


class MicClient(AsyncClient):
    def __init__(self) -> None:
        super().__init__()

    async def read_event(self) -> Optional[Event]:
        await asyncio.sleep(AUDIO_CHUNK.seconds)
        return AUDIO_CHUNK.event()

    async def write_event(self, event: Event) -> None:
        # Output only
        pass


class WakeClient(AsyncClient):
    def __init__(self) -> None:
        super().__init__()
        self._event_ready = asyncio.Event()
        self._event: Optional[Event] = None
        self._detected: bool = False

    async def read_event(self) -> Optional[Event]:
        await self._event_ready.wait()
        self._event_ready.clear()
        return self._event

    async def write_event(self, event: Event) -> None:
        if AudioChunk.is_type(event.type):
            if not self._detected:
                self._detected = True
                self._event = Detection().event()
                self._event_ready.set()


class EventClient(AsyncClient):
    def __init__(self) -> None:
        super().__init__()
        self.detection = asyncio.Event()
        self.streaming_started = asyncio.Event()
        self.streaming_stopped = asyncio.Event()

    async def read_event(self) -> Optional[Event]:
        # Input only
        return None

    async def write_event(self, event: Event) -> None:
        if Detection.is_type(event.type):
            self.detection.set()
        elif StreamingStarted.is_type(event.type):
            self.streaming_started.set()
        elif StreamingStopped.is_type(event.type):
            self.streaming_stopped.set()


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


@pytest.mark.asyncio
async def test_satellite_and_server(tmp_path: Path) -> None:
    mic_client = MicClient()
    wake_client = WakeClient()
    event_client = EventClient()

    with patch(
        "wyoming_satellite.satellite.SatelliteBase._make_mic_client",
        return_value=mic_client,
    ), patch(
        "wyoming_satellite.satellite.SatelliteBase._make_wake_client",
        return_value=wake_client,
    ), patch(
        "wyoming_satellite.satellite.SatelliteBase._make_event_client",
        return_value=event_client,
    ):
        satellite = WakeStreamingSatellite(
            SatelliteSettings(
                mic=MicSettings(uri="test"),
                wake=WakeSettings(uri="test"),
                event=EventSettings(uri="test"),
            )
        )

        # Fake server connection
        server_io = FakeStreamReaderWriter()
        await satellite.set_server("test", server_io)  # type: ignore

        async def event_from_satellite() -> Optional[Event]:
            return await async_read_event(server_io)

        satellite_task = asyncio.create_task(satellite.run(), name="satellite")
        await satellite.event_from_server(RunSatellite().event())

        # Trigger detection
        event = await asyncio.wait_for(event_from_satellite(), timeout=TIMEOUT)
        assert event is not None
        assert Detection.is_type(event.type), event

        # Pipeline should start
        event = await asyncio.wait_for(event_from_satellite(), timeout=TIMEOUT)
        assert event is not None
        assert RunPipeline.is_type(event.type), event
        run_pipeline = RunPipeline.from_event(event)
        assert run_pipeline.start_stage == PipelineStage.ASR

        # No TTS
        assert run_pipeline.end_stage == PipelineStage.HANDLE

        # Event service should have received detection
        await asyncio.wait_for(event_client.detection.wait(), timeout=TIMEOUT)

        # Server should be receiving audio now
        assert satellite.is_streaming, "Not streaming"
        for _ in range(5):
            event = await asyncio.wait_for(event_from_satellite(), timeout=TIMEOUT)
            assert event is not None
            assert AudioChunk.is_type(event.type)

        # Event service should have received streaming start
        await asyncio.wait_for(event_client.streaming_started.wait(), timeout=TIMEOUT)

        # Send transcript
        await satellite.event_from_server(Transcript(text="test").event())

        # Wait for streaming to stop
        while satellite.is_streaming:
            event = await asyncio.wait_for(event_from_satellite(), timeout=TIMEOUT)
            assert event is not None
            assert AudioChunk.is_type(event.type)

        # Event service should have received streaming stop
        await asyncio.wait_for(event_client.streaming_stopped.wait(), timeout=TIMEOUT)

        await satellite.stop()
        await satellite_task
