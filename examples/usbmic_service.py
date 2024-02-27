#!/usr/bin/env python3
"""Controls the LEDs on the ReSpeaker Mic Array v2.0 (USB) ."""
import argparse
import asyncio
import logging
import time
from functools import partial

from wyoming.event import Event
from wyoming.satellite import (
    SatelliteConnected,
    SatelliteDisconnected,
    StreamingStarted,
    StreamingStopped,
)
from wyoming.snd import Played
from wyoming.server import AsyncEventHandler, AsyncServer
from wyoming.vad import VoiceStarted, VoiceStopped
from wyoming.wake import Detection

from pixel_ring import pixel_ring

_LOGGER = logging.getLogger()

async def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--uri", required=True, help="unix:// or tcp://")
    parser.add_argument("--debug", action="store_true", help="Log DEBUG messages")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO)
    _LOGGER.debug(args)

    _LOGGER.info("Ready")

    # Turn on power to LEDs
    pixel_ring.set_color_palette(0x0080ff, 0x007a37)
    pixel_ring.think()
    await asyncio.sleep(3)
    pixel_ring.off()

    # Start server
    server = AsyncServer.from_uri(args.uri)

    try:
        await server.run(partial(LEDsEventHandler, args))
    except KeyboardInterrupt:
        pass
    finally:
        pixel_ring.off()


class LEDsEventHandler(AsyncEventHandler):
    """Event handler for clients."""

    def __init__(
        self,
        cli_args: argparse.Namespace,
        *args,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)

        self.cli_args = cli_args
        self.client_id = str(time.monotonic_ns())

        _LOGGER.debug("Client connected: %s", self.client_id)

    async def handle_event(self, event: Event) -> bool:
        _LOGGER.debug(event)

        if Detection.is_type(event.type):
            _LOGGER.debug("Detection")
            pixel_ring.wakeup()
        elif VoiceStarted.is_type(event.type):
            _LOGGER.debug("VoiceStarted")
            pixel_ring.speak()
        elif VoiceStopped.is_type(event.type):
            _LOGGER.debug("VoiceStopped")
            pixel_ring.spin()
        elif StreamingStopped.is_type(event.type):
            _LOGGER.debug("StreamingStopped")
            pixel_ring.off()
        elif SatelliteConnected.is_type(event.type):
            _LOGGER.debug("SatelliteConnected")
            pixel_ring.think()
            await asyncio.sleep(2)
            pixel_ring.off()
        elif Played.is_type(event.type):
            _LOGGER.debug("Played")
            pixel_ring.off()
        elif SatelliteDisconnected.is_type(event.type):
            _LOGGER.debug("SatelliteDisconnected")
            pixel_ring.mono(0xff0000)

        return True

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
