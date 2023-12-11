#!/usr/bin/env python3
import argparse
import asyncio
import logging
import time
from functools import partial

from wyoming.event import Event
from wyoming.server import AsyncEventHandler, AsyncServer

_LOGGER = logging.getLogger()


async def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--uri", default="stdio://", help="unix:// or tcp://")
    #
    parser.add_argument("--debug", action="store_true", help="Log DEBUG messages")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO)
    _LOGGER.debug(args)

    _LOGGER.info("Ready")

    # Start server
    server = AsyncServer.from_uri(args.uri)

    try:
        await server.run(partial(ExampleEventHandler, args))
    except KeyboardInterrupt:
        pass


# -----------------------------------------------------------------------------


class ExampleEventHandler(AsyncEventHandler):
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
        _LOGGER.info(event)

        return True


# -----------------------------------------------------------------------------

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
