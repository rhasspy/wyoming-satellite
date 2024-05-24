#!/usr/bin/env python3
import argparse
import asyncio
import json
import logging
from functools import partial
from typing import Optional

import websockets
from wyoming.event import Event
from wyoming.server import AsyncEventHandler, AsyncServer

_LOGGER = logging.getLogger()


async def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--uri", required=True, help="unix:// or tcp://")
    parser.add_argument("--websocket-host", default="localhost")
    parser.add_argument("--websocket-port", type=int, default=8675)
    #
    parser.add_argument("--debug", action="store_true", help="Log DEBUG messages")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO)
    _LOGGER.debug(args)

    _LOGGER.info("Ready")

    # Start server
    server = AsyncServer.from_uri(args.uri)
    queue: "asyncio.Queue[Optional[Event]]" = asyncio.Queue()

    try:
        async with websockets.serve(
            partial(websocket_connected, queue),
            args.websocket_host,
            args.websocket_port,
        ):
            await server.run(partial(WebsocketEventHandler, args, queue))
    finally:
        queue.put_nowait(None)


# -----------------------------------------------------------------------------


async def websocket_connected(queue: "asyncio.Queue[Optional[Event]]", websocket):
    try:
        while True:
            event = await queue.get()
            if event is None:
                # Stop signal
                break

            await websocket.send(
                json.dumps(
                    {"type": event.type, "data": event.data or {}}, ensure_ascii=False
                )
            )
    except websockets.ConnectionClosed:
        pass
    except Exception:
        _LOGGER.exception("Error in websocket handler")


# -----------------------------------------------------------------------------


class WebsocketEventHandler(AsyncEventHandler):
    """Event handler for clients."""

    def __init__(
        self,
        cli_args: argparse.Namespace,
        queue: "asyncio.Queue[Optional[Event]]",
        *args,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)

        self.cli_args = cli_args
        self.queue = queue

    async def handle_event(self, event: Event) -> bool:
        _LOGGER.debug(event)
        self.queue.put_nowait(event)

        return True


# -----------------------------------------------------------------------------


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
