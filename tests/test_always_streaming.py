import asyncio
import logging
import os
from pathlib import Path

import pytest
from wyoming.audio import AudioChunk
from wyoming.wake import Detection
from wyoming.client import AsyncClient
from wyoming.event import Event, async_write_event
from wyoming.server import AsyncServer, AsyncEventHandler
from wyoming_satellite import (
    AlwaysStreamingSatellite,
    EventSettings,
    SatelliteSettings,
    MicSettings,
    WakeSettings,
)

from .shared import WYOMING_INFO, AUDIO_CHUNK

_LOGGER = logging.getLogger()

class MicEventHandler(AsyncEventHandler):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._is_connected = True
        self._task = asyncio.create_task(self.stream_audio())

    async def handle_event(self, event: Event) -> bool:
        """Output only."""
        return True

    async def stream_audio(self) -> None:
        while self._is_connected:
            await self.write_event(AUDIO_CHUNK.event())
            await asyncio.sleep(AUDIO_CHUNK.seconds)

    async def disconnect(self) -> None:
        self._is_connected = False
        await self._task


class WakeEventHandler(AsyncEventHandler):
    async def handle_event(self, event: Event) -> bool:
        _LOGGER.error(event)
        if AudioChunk.is_type(event.type):
            await self.write_event(Detection().event())

        return True


@pytest.mark.asyncio
async def test_multiple_wakeups(tmp_path: Path) -> None:
    mic_socket = tmp_path / "mic.socket"
    os.mkfifo(mic_socket)
    mic_uri = f"unix://{mic_socket}"
    mic_server = AsyncServer.from_uri(mic_uri)
    mic_task = asyncio.create_task(mic_server.run(MicEventHandler))

    wake_socket = tmp_path / "wake.socket"
    os.mkfifo(wake_socket)
    wake_uri = f"unix://{wake_socket}"
    wake_server = AsyncServer.from_uri(wake_uri)
    wake_task = asyncio.create_task(wake_server.run(WakeEventHandler))

    wake_event = asyncio.Event()

    class EventEventHandler(AsyncEventHandler):
        async def handle_event(self, event: Event) -> bool:
            if Detection.is_type(event.type):
                wake_event.set()

            return True

    event_socket = tmp_path / "event.socket"
    os.mkfifo(event_socket)
    event_uri = f"unix://{event_socket}"
    event_server = AsyncServer.from_uri(event_uri)
    event_task = asyncio.create_task(event_server.run(EventEventHandler))

    satellite = AlwaysStreamingSatellite(
        SatelliteSettings(
            mic=MicSettings(uri=mic_uri),
            wake=WakeSettings(uri=wake_uri),
            event=EventSettings(uri=event_uri),
        )
    )

    satellite_task = asyncio.create_task(satellite.run())

    await asyncio.sleep(0.5)

    # async with asyncio.timeout(1):
    #     await wake_event.wait()

    # await satellite.stop()

    tasks = [mic_task, wake_task, event_task]
    for task in tasks:
        task.cancel()
    await asyncio.wait(tasks)
