import asyncio
import logging
from typing import Final, Optional
from unittest.mock import patch

import pytest
from wyoming.asr import Transcript
from wyoming.audio import AudioChunk, AudioStart, AudioStop
from wyoming.client import AsyncClient
from wyoming.event import Event, async_read_event
from wyoming.pipeline import PipelineStage, RunPipeline
from wyoming.satellite import RunSatellite, StreamingStarted, StreamingStopped
from wyoming.tts import Synthesize
from wyoming.wake import Detection

from wyoming_satellite import (
    EventSettings,
    MicSettings,
    SatelliteSettings,
    SndSettings,
    WakeSettings,
    WakeStreamingSatellite,
)

from .shared import (
    AUDIO_CHUNK,
    AUDIO_START,
    AUDIO_STOP,
    FakeStreamReaderWriter,
    MicClient,
)

_LOGGER = logging.getLogger()

TIMEOUT: Final = 1


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


class SndClient(AsyncClient):
    def __init__(self) -> None:
        super().__init__()
        self.synthesize = asyncio.Event()
        self.audio_start = asyncio.Event()
        self.audio_chunk = asyncio.Event()
        self.audio_stop = asyncio.Event()

    async def read_event(self) -> Optional[Event]:
        # Input only
        pass

    async def write_event(self, event: Event) -> None:
        if AudioChunk.is_type(event.type):
            self.audio_chunk.set()
        elif Synthesize.is_type(event.type):
            self.synthesize.set()
        elif AudioStart.is_type(event.type):
            self.audio_start.set()
        elif AudioStop.is_type(event.type):
            self.audio_stop.set()


class EventClient(AsyncClient):
    def __init__(self) -> None:
        super().__init__()
        self.detection = asyncio.Event()
        self.streaming_started = asyncio.Event()
        self.streaming_stopped = asyncio.Event()
        self.transcript = asyncio.Event()
        self.synthesize = asyncio.Event()
        self.audio_start = asyncio.Event()
        self.audio_chunk = asyncio.Event()
        self.audio_stop = asyncio.Event()

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
        elif Transcript.is_type(event.type):
            self.transcript.set()
        elif Synthesize.is_type(event.type):
            self.synthesize.set()
        elif AudioChunk.is_type(event.type):
            self.audio_chunk.set()
        elif AudioStart.is_type(event.type):
            self.audio_start.set()
        elif AudioStop.is_type(event.type):
            self.audio_stop.set()


# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_wake_satellite() -> None:
    mic_client = MicClient()
    snd_client = SndClient()
    wake_client = WakeClient()
    event_client = EventClient()

    with patch(
        "wyoming_satellite.satellite.SatelliteBase._make_mic_client",
        return_value=mic_client,
    ), patch(
        "wyoming_satellite.satellite.SatelliteBase._make_snd_client",
        return_value=snd_client,
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
                snd=SndSettings(uri="test"),
                wake=WakeSettings(uri="test"),
                event=EventSettings(uri="test"),
            )
        )

        async def event_from_satellite() -> Optional[Event]:
            return await async_read_event(server_io)

        satellite_task = asyncio.create_task(satellite.run(), name="satellite")

        # Fake server connection
        server_io = FakeStreamReaderWriter()
        await satellite.set_server("test", server_io)  # type: ignore

        # Start satellite
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
        assert run_pipeline.end_stage == PipelineStage.TTS

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

        # Event service should have received transcript
        await asyncio.wait_for(event_client.transcript.wait(), timeout=TIMEOUT)

        # Wait for streaming to stop
        while satellite.is_streaming:
            event = await asyncio.wait_for(event_from_satellite(), timeout=TIMEOUT)
            assert event is not None
            assert AudioChunk.is_type(event.type)

        # Event service should have received streaming stop
        await asyncio.wait_for(event_client.streaming_stopped.wait(), timeout=TIMEOUT)

        # Fake a TTS response
        await satellite.event_from_server(Synthesize(text="test").event())

        # Event service should have received synthesize
        await asyncio.wait_for(event_client.synthesize.wait(), timeout=TIMEOUT)

        # Audio start, chunk, stop
        await satellite.event_from_server(AUDIO_START.event())
        await asyncio.wait_for(snd_client.audio_start.wait(), timeout=TIMEOUT)
        await asyncio.wait_for(event_client.audio_start.wait(), timeout=TIMEOUT)

        # Event service does not get audio chunks, just start/stop
        await satellite.event_from_server(AUDIO_CHUNK.event())
        await asyncio.wait_for(snd_client.audio_chunk.wait(), timeout=TIMEOUT)

        await satellite.event_from_server(AUDIO_STOP.event())
        await asyncio.wait_for(snd_client.audio_stop.wait(), timeout=TIMEOUT)
        await asyncio.wait_for(event_client.audio_stop.wait(), timeout=TIMEOUT)

        # Stop satellite
        await satellite.stop()
        await satellite_task
