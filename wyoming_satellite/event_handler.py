"""Wyoming event handler for satellites."""
import argparse
import logging
import time

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
        *args,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)

        self.cli_args = cli_args
        self.wyoming_info = wyoming_info
        self.client_id = str(time.monotonic_ns())
        self.satellite = satellite

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

        await self.satellite.event_from_server(event)

        return True

    async def disconnect(self) -> None:
        """Server disconnect."""
        if self.satellite.server_id == self.client_id:
            await self.satellite.clear_server()
