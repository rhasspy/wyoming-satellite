"""Wyoming event handler for satellites."""
import argparse
import asyncio
import logging
import time
from typing import Optional

from wyoming.event import Event
from wyoming.info import Describe, Info
from wyoming.server import AsyncEventHandler

from .satellite import SatelliteBase

_LOGGER = logging.getLogger()


class SatelliteEventHandler(AsyncEventHandler):
    """Event handler for clients."""

    def __init__(
        self,
        wyoming_info: Info,
        satellite: SatelliteBase,
        cli_args: argparse.Namespace,
        queue: asyncio.Queue[Optional[Event]] | None, 
        *args,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)

        self.cli_args = cli_args
        self.client_id = str(time.monotonic_ns())
        self.queue = queue
        self.satellite = satellite
        self.wyoming_info = wyoming_info


    # -------------------------------------------------------------------------

    async def handle_event(self, event: Event) -> bool:
        """Handle events from the server."""
        if Describe.is_type(event.type):
            await self.satellite.update_info(self.wyoming_info)
            await self.write_event(self.wyoming_info.event())
            return True

        if self.satellite.server_id is None:
            # Take over after a problem occurred
            await self.satellite.set_server(self.client_id, self.writer)
        elif self.satellite.server_id != self.client_id:
            # New connection
            _LOGGER.debug("Connection cancelled: %s", self.client_id)
            return False
        
        if self.queue:
            await self.queue.put(event)

        await self.satellite.event_from_server(event)

        return True

    async def disconnect(self) -> None:
        """Server disconnect."""
        if self.satellite.server_id == self.client_id:
            await self.satellite.clear_server()
