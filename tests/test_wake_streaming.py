import asyncio
import logging
from pathlib import Path
from typing import Optional
from unittest.mock import patch

import pytest
from wyoming.asr import Transcript
from wyoming.audio import AudioChunk
from wyoming.client import AsyncClient
from wyoming.event import Event
from wyoming.satellite import RunSatellite
from wyoming.wake import Detection

from wyoming_satellite import (
    EventSettings,
    MicSettings,
    SatelliteSettings,
    WakeSettings,
    WakeStreamingSatellite,
)

from .shared import MicClient

_LOGGER = logging.getLogger()


class WakeClient(AsyncClient):
    def __init__(self) -> None:
        super().__init__()
        self._detection_event = asyncio.Event()

    async def read_event(self) -> Optional[Event]:
        await self._detection_event.wait()
        return Detection().event()

    async def write_event(self, event: Event) -> None:
        if AudioChunk.is_type(event.type):
            self._detection_event.set()


class EventClient(AsyncClient):
    def __init__(self) -> None:
        super().__init__()
        self.wake_event = asyncio.Event()

    async def read_event(self) -> Optional[Event]:
        # Input only
        return None

    async def write_event(self, event: Event) -> None:
        if Detection.is_type(event.type):
            self.wake_event.set()


@pytest.mark.asyncio
async def test_multiple_wakeups(tmp_path: Path) -> None:
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
        satellite.server_id = "test"

        satellite_task = asyncio.create_task(satellite.run(), name="satellite")
        await satellite.event_from_server(RunSatellite().event())

        await asyncio.wait_for(event_client.wake_event.wait(), timeout=1)
        event_client.wake_event.clear()

        # Stop streaming
        await satellite.event_from_server(Transcript("test").event())

        # Should not trigger again within refractory period (default: 5 sec)
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(event_client.wake_event.wait(), timeout=0.15)

        await satellite.stop()
        await satellite_task
