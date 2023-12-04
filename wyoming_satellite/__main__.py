#!/usr/bin/env python3
import argparse
import asyncio
import logging
import time
import uuid
from enum import Enum
from functools import partial
from pathlib import Path
from typing import Optional

from wyoming.asr import Transcript, Transcribe
from wyoming.audio import AudioChunk, AudioStart, AudioStop
from wyoming.client import AsyncClient
from wyoming.event import Event
from wyoming.info import Attribution, Describe, Info, Satellite
from wyoming.pipeline import PipelineStage, RunPipeline
from wyoming.satellite import RunSatellite
from wyoming.server import AsyncEventHandler, AsyncServer, AsyncTcpServer
from wyoming.tts import Synthesize
from wyoming.vad import VoiceStarted, VoiceStopped
from wyoming.wake import Detect, Detection

_LOGGER = logging.getLogger()
_DIR = Path(__file__).parent


class SatelliteState(str, Enum):
    WAKE = "wake"
    ASR = "asr"


async def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mic-uri", required=True, help="URI of Wyoming microphone service"
    )
    #
    parser.add_argument("--snd-uri", help="URI of Wyoming sound service")
    parser.add_argument("--wake-uri", help="URI of Wyoming wake word detection service")
    parser.add_argument(
        "--wake-word-name",
        action="append",
        default=[],
        help="Name of wake word to listen for (requires --wake-uri)",
    )
    #
    parser.add_argument(
        "--event-uri", help="URI of Wyoming service to forward events to"
    )
    #
    parser.add_argument("--uri", default="stdio://", help="unix:// or tcp://")
    parser.add_argument("--name", required=True, help="Name of the satellite")
    parser.add_argument("--area", help="Area name of the satellite")
    parser.add_argument("--pipeline", help="Name of server pipeline to run")
    #
    parser.add_argument(
        "--no-zeroconf", action="store_true", help="Disable discovery over zeroconf"
    )
    parser.add_argument(
        "--zeroconf-name",
        help="Name used for zeroconf discovery (default: MAC from uuid.getnode)",
    )
    #
    parser.add_argument("--debug", action="store_true", help="Log DEBUG messages")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO)
    _LOGGER.debug(args)

    wyoming_info = Info(
        satellite=Satellite(
            name=args.name,
            area=args.area,
            description=args.name,
            attribution=Attribution(name="", url=""),
            installed=True,
        )
    )

    _LOGGER.info("Ready")

    # Start server
    server = AsyncServer.from_uri(args.uri)

    if (not args.no_zeroconf) and isinstance(server, AsyncTcpServer):
        from wyoming.zeroconf import register_server

        if not args.zeroconf_name:
            args.zeroconf_name = get_mac_address()

        tcp_server: AsyncTcpServer = server
        await register_server(
            name=args.zeroconf_name,
            port=tcp_server.port,
            host=tcp_server.host,
        )
        _LOGGER.debug("Zeroconf discovery enabled (name=%s)", args.zeroconf_name)

    try:
        await server.run(partial(SatelliteEventHandler, wyoming_info, args))
    except KeyboardInterrupt:
        pass


# -----------------------------------------------------------------------------


class SatelliteEventHandler(AsyncEventHandler):
    """Event handler for clients."""

    def __init__(
        self,
        wyoming_info: Info,
        cli_args: argparse.Namespace,
        *args,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)

        self.cli_args = cli_args
        self.wyoming_info_event = wyoming_info.event()
        self.client_id = str(time.monotonic_ns())

        self.state: Optional[Satellite] = None
        self.satellite_task: Optional[asyncio.Task] = None
        self.has_snd = bool(self.cli_args.snd_uri)
        self.snd_client: Optional[AsyncClient] = None
        self.events_client: Optional[AsyncClient] = None
        self.is_running = True

        _LOGGER.debug("Client connected: %s", self.client_id)

    async def handle_event(self, event: Event) -> bool:
        if Describe.is_type(event.type):
            await self.write_event(self.wyoming_info_event)
            _LOGGER.debug("Sent info to client: %s", self.client_id)
            return True

        if RunSatellite.is_type(event.type) and (self.satellite_task is None):
            if self.cli_args.wake_uri:
                # Local wake word detection
                await self.write_event(
                    RunPipeline(
                        start_stage=PipelineStage.ASR,
                        end_stage=PipelineStage.TTS
                        if self.has_snd
                        else PipelineStage.HANDLE,
                        name=self.cli_args.pipeline,
                    ).event()
                )
                self.state = SatelliteState.WAKE
                self.satellite_task = asyncio.create_task(self.run_satellite_wake())
            else:
                # Remote wake word detection
                await self.write_event(
                    RunPipeline(
                        start_stage=PipelineStage.WAKE,
                        end_stage=PipelineStage.TTS
                        if self.has_snd
                        else PipelineStage.HANDLE,
                        name=self.cli_args.pipeline,
                    ).event()
                )
                self.state = None
                self.satellite_task = asyncio.create_task(self.run_satellite())
        elif Transcript.is_type(event.type):
            if self.state == SatelliteState.ASR:
                # Ready for next wake word detection
                self.state = SatelliteState.WAKE
                _LOGGER.info("Detecting wake word")

            # STT transcript
            await self.forward_event(event)
        elif self.has_snd and (
            AudioStart.is_type(event.type)
            or AudioChunk.is_type(event.type)
            or AudioStop.is_type(event.type)
        ):
            if self.snd_client is None:
                self.snd_client = AsyncClient.from_uri(self.cli_args.snd_uri)
                await self.snd_client.connect()

            assert self.snd_client is not None

            try:
                # Forward to sound service
                await self.snd_client.write_event(event)
            except Exception:
                _LOGGER.exception("Unexpected error while sending snd audio")

                # Reconnect
                self.snd_client = None

            if AudioStart.is_type(event.type) or AudioStop.is_type(event.type):
                # TTS start/stop
                await self.forward_event(event)
        elif (
            Detect.is_type(event.type)
            or Detection.is_type(event.type)
            or Transcribe.is_type(event.type)
            or VoiceStarted.is_type(event.type)
            or VoiceStopped.is_type(event.type)
            or Synthesize.is_type(event.type)
        ):
            # Other client events:
            # - Detect for start of wake word detection
            # - Detection for when wake word is detected
            # - Transcribe for when STT starts
            # - VoiceStarted/VoiceStopped for when user starts/stops speaking
            # - Synthesize for TTS text
            await self.forward_event(event)
        else:
            _LOGGER.debug("Unexpected event: type=%s, data=%s", event.type, event.data)

        return True

    async def run_satellite(self) -> None:
        try:
            _LOGGER.debug("Connecting to %s", self.cli_args.mic_uri)
            async with AsyncClient.from_uri(self.cli_args.mic_uri) as mic_client:
                _LOGGER.info("Streaming audio")

                while True:
                    mic_event = await mic_client.read_event()
                    if mic_event is None:
                        _LOGGER.warning("Microphone service disconnected")
                        break

                    if AudioChunk.is_type(mic_event.type):
                        # Forward all audio to server
                        await self.write_event(mic_event)

        except Exception:
            _LOGGER.exception("Unexpected error in run_satellite")

    async def run_satellite_wake(self) -> None:
        try:
            assert self.cli_args.wake_uri

            _LOGGER.debug("Connecting to %s", self.cli_args.mic_uri)
            _LOGGER.debug("Connecting to %s", self.cli_args.wake_uri)

            async with AsyncClient.from_uri(
                self.cli_args.mic_uri
            ) as mic_client, AsyncClient.from_uri(
                self.cli_args.wake_uri
            ) as wake_client:
                _LOGGER.info("Detecting wake word")

                if self.cli_args.wake_word_name:
                    # Request specific wake word(s)
                    detect_event = Detect(names=self.cli_args.wake_word_name).event()
                else:
                    detect_event = Detect().event()

                await wake_client.write_event(detect_event)
                await self.forward_event(detect_event)

                # Read events in parallel
                mic_task = asyncio.create_task(mic_client.read_event())
                wake_task = asyncio.create_task(wake_client.read_event())
                pending = {mic_task, wake_task}

                while self.is_running:
                    done, pending = await asyncio.wait(
                        pending, return_when=asyncio.FIRST_COMPLETED
                    )

                    if mic_task in done:
                        mic_event = mic_task.result()
                        if mic_event is None:
                            _LOGGER.warning("Microphone service disconnected")
                            break

                        if AudioChunk.is_type(mic_event.type):
                            # Forward to wake service
                            await wake_client.write_event(mic_event)

                            if self.state == SatelliteState.ASR:
                                # Forward to server
                                await self.write_event(mic_event)

                        # Next audio chunk
                        mic_task = asyncio.create_task(mic_client.read_event())
                        pending.add(mic_task)
                    elif wake_task in done:
                        wake_event = wake_task.result()
                        if wake_event is None:
                            _LOGGER.warning("Wake word service disconnected")
                            break

                        if Detection.is_type(wake_event.type) and (
                            self.state == SatelliteState.WAKE
                        ):
                            _LOGGER.debug("Wake word detected: %s", wake_event)
                            self.state = SatelliteState.ASR

                            # Forward to server
                            await self.write_event(wake_event)

                            # Forward to client
                            await self.forward_event(wake_event)

                            _LOGGER.info("Streaming audio")

                        # Next wake event
                        wake_task = asyncio.create_task(wake_client.read_event())
                        pending.add(wake_task)
        except Exception:
            _LOGGER.exception("Unexpected error in run_satellite")

    async def forward_event(self, event: Event) -> None:
        """Forward a Wyoming event to a client."""
        if not self.cli_args.event_uri:
            return

        if self.events_client is None:
            self.events_client = AsyncClient.from_uri(self.cli_args.event_uri)
            _LOGGER.debug("Connecting to %s", self.cli_args.event_uri)
            await self.events_client.connect()

        assert self.events_client is not None
        await self.events_client.write_event(event)

    async def disconnect(self) -> None:
        self.is_running = False


# -----------------------------------------------------------------------------


def get_mac_address() -> str:
    """Return MAC address formatted as hex with no colons."""
    return "".join(
        ["{:02x}".format((uuid.getnode() >> ele) & 0xFF) for ele in range(0, 8 * 6, 8)][
            ::-1
        ]
    )


# -----------------------------------------------------------------------------

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
