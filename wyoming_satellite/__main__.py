#!/usr/bin/env python3
import argparse
import asyncio
import logging
import shlex
import sys
import time
import uuid
from enum import Enum
from functools import partial
from pathlib import Path
from typing import Callable, Final, Optional

from wyoming.asr import Transcribe, Transcript
from wyoming.audio import AudioChunk, AudioStart, AudioStop
from wyoming.client import AsyncClient
from wyoming.event import Event
from wyoming.info import Attribution, Describe, Info, Satellite
from wyoming.mic import MicProcessAsyncClient
from wyoming.pipeline import PipelineStage, RunPipeline
from wyoming.satellite import RunSatellite
from wyoming.server import AsyncEventHandler, AsyncServer, AsyncTcpServer
from wyoming.snd import SndProcessAsyncClient
from wyoming.tts import Synthesize
from wyoming.vad import VoiceStarted, VoiceStopped
from wyoming.wake import Detect, Detection, WakeProcessAsyncClient

from .utils import AudioBuffer, chunk_samples, multiply_volume

_LOGGER = logging.getLogger()
_DIR = Path(__file__).parent


class SatelliteState(str, Enum):
    WAKE = "wake"
    ASR = "asr"


async def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser()

    # Microphone input
    parser.add_argument("--mic-uri", help="URI of Wyoming microphone service")
    parser.add_argument("--mic-command", help="Program to run for microphone input")
    parser.add_argument(
        "--mic-command-rate",
        type=int,
        default=16000,
        help="Sample rate of mic-command (hertz, default: 16000)",
    )
    parser.add_argument(
        "--mic-command-width",
        type=int,
        default=2,
        help="Sample width of mic-command (bytes, default: 2)",
    )
    parser.add_argument(
        "--mic-command-channels",
        type=int,
        default=1,
        help="Sample channels of mic-command (default: 1)",
    )
    parser.add_argument(
        "--mic-command-samples-per-chunk",
        type=int,
        default=1024,
        help="Sample per chunk for mic-command (default: 1024)",
    )

    # Sound output
    parser.add_argument("--snd-uri", help="URI of Wyoming sound service")
    parser.add_argument("--snd-command", help="Program to run for sound output")
    parser.add_argument(
        "--snd-command-rate",
        type=int,
        default=22050,
        help="Sample rate of snd-command (hertz, default: 22050)",
    )
    parser.add_argument(
        "--snd-command-width",
        type=int,
        default=2,
        help="Sample width of snd-command (bytes, default: 2)",
    )
    parser.add_argument(
        "--snd-command-channels",
        type=int,
        default=1,
        help="Sample channels of snd-command (default: 1)",
    )

    # Local wake word detection
    parser.add_argument("--wake-uri", help="URI of Wyoming wake word detection service")
    parser.add_argument(
        "--wake-word-name",
        action="append",
        default=[],
        help="Name of wake word to listen for (requires --wake-uri)",
    )
    parser.add_argument("--wake-command", help="Program to run for wake word detection")
    parser.add_argument(
        "--wake-command-rate",
        type=int,
        default=16000,
        help="Sample rate of wake-command (hertz, default: 16000)",
    )
    parser.add_argument(
        "--wake-command-width",
        type=int,
        default=2,
        help="Sample width of wake-command (bytes, default: 2)",
    )
    parser.add_argument(
        "--wake-command-channels",
        type=int,
        default=1,
        help="Sample channels of wake-command (default: 1)",
    )

    # Voice activity detector
    parser.add_argument(
        "--vad", choices=("disabled", "webrtcvad", "silero"), default="disabled"
    )
    parser.add_argument("--vad-threshold", type=float, default=0.5)
    parser.add_argument("--vad-trigger-level", type=int, default=3)
    parser.add_argument("--vad-buffer-chunks", type=int, default=40)

    # Audio enhancement (requires webrtc-noise-audio)
    parser.add_argument(
        "--noise-suppression", type=int, default=0, choices=(0, 1, 2, 3, 4)
    )
    parser.add_argument("--auto-gain", type=int, default=0, choices=list(range(32)))
    parser.add_argument("--volume-multiplier", type=float, default=1.0)

    # External event handlers
    parser.add_argument(
        "--event-uri", help="URI of Wyoming service to forward events to"
    )

    # Satellite details
    parser.add_argument("--uri", default="stdio://", help="unix:// or tcp://")
    parser.add_argument("--name", required=True, help="Name of the satellite")
    parser.add_argument("--area", help="Area name of the satellite")
    parser.add_argument("--pipeline", help="Name of server pipeline to run")

    # Zeroconf
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

    # Validate args
    if (not args.mic_uri) and (not args.mic_command):
        _LOGGER.fatal("Either --mic-uri or --mic-command is required")
        sys.exit(1)

    if needs_webrtc(args):
        try:
            import webrtc_noise_gain  # noqa: F401
        except ImportError:
            _LOGGER.fatal("Install extras for webrtc")
            sys.exit(1)

    if needs_silero(args):
        try:
            import pysilero_vad  # noqa: F401
        except ImportError:
            _LOGGER.fatal("Install extras for silero")
            sys.exit(1)

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
        self.volume_multiplier = self.cli_args.volume_multiplier
        self.has_audio_processing = needs_webrtc(self.cli_args) or (
            self.volume_multiplier != 1.0
        )
        self.has_wake = bool(self.cli_args.wake_uri or self.cli_args.wake_command)
        self.has_snd = bool(self.cli_args.snd_uri or self.cli_args.snd_command)
        self.snd_client: Optional[AsyncClient] = None
        self.events_client: Optional[AsyncClient] = None
        self.is_running = True

        self.process_webrtc: Optional[Callable[[bytes], bytes]] = None
        if needs_webrtc(self.cli_args):
            self.process_webrtc = WebRtcAudio(
                self.cli_args.auto_gain, self.cli_args.noise_suppression
            )

        _LOGGER.debug("Client connected: %s", self.client_id)

    async def handle_event(self, event: Event) -> bool:
        if Describe.is_type(event.type):
            await self.write_event(self.wyoming_info_event)
            _LOGGER.debug("Sent info to client: %s", self.client_id)
            return True

        if RunSatellite.is_type(event.type) and (self.satellite_task is None):
            if self.has_wake:
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
            _LOGGER.debug(event)
        elif self.has_snd and (
            AudioStart.is_type(event.type)
            or AudioChunk.is_type(event.type)
            or AudioStop.is_type(event.type)
        ):
            if self.snd_client is None:
                if self.cli_args.snd_command:
                    _LOGGER.debug("Running %s", self.cli_args.snd_command)
                    program, *program_args = shlex.split(self.cli_args.snd_command)
                    self.snd_client = SndProcessAsyncClient(
                        rate=self.cli_args.snd_command_rate,
                        width=self.cli_args.snd_command_width,
                        channels=self.cli_args.snd_command_channels,
                        program=program,
                        program_args=program_args,
                    )
                else:
                    _LOGGER.debug("Connecting to %s", self.cli_args.snd_uri)
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
                _LOGGER.debug(event)
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
            _LOGGER.debug(event)
        else:
            _LOGGER.debug("Unexpected event: type=%s, data=%s", event.type, event.data)

        return True

    def _make_mic_client(self) -> AsyncClient:
        if self.cli_args.mic_command:
            _LOGGER.debug("Running %s", self.cli_args.mic_command)
            program, *program_args = shlex.split(self.cli_args.mic_command)
            return MicProcessAsyncClient(
                rate=self.cli_args.mic_command_rate,
                width=self.cli_args.mic_command_width,
                channels=self.cli_args.mic_command_channels,
                samples_per_chunk=self.cli_args.mic_command_samples_per_chunk,
                program=program,
                program_args=program_args,
            )

        assert self.cli_args.mic_uri
        _LOGGER.debug("Connecting to %s", self.cli_args.mic_uri)
        return AsyncClient.from_uri(self.cli_args.mic_uri)

    async def run_satellite(self) -> None:
        try:
            mic_client = self._make_mic_client()
            async with mic_client:
                _LOGGER.info("Streaming audio")

                while True:
                    mic_event = await mic_client.read_event()
                    if mic_event is None:
                        _LOGGER.warning("Microphone service disconnected")
                        break

                    if AudioChunk.is_type(mic_event.type):
                        mic_event = self._process_audio(mic_event)

                        # Forward all audio to server
                        await self.write_event(mic_event)

        except Exception:
            _LOGGER.exception("Unexpected error in run_satellite")

    async def run_satellite_wake(self) -> None:
        try:
            assert self.cli_args.wake_uri or self.cli_args.wake_command

            mic_client = self._make_mic_client()

            if self.cli_args.wake_command:
                _LOGGER.debug("Running %s", self.cli_args.wake_command)
                program, *program_args = shlex.split(self.cli_args.wake_command)
                wake_client = WakeProcessAsyncClient(
                    rate=self.cli_args.wake_command_rate,
                    width=self.cli_args.wake_command_width,
                    channels=self.cli_args.wake_command_channels,
                    program=program,
                    program_args=program_args,
                )
            else:
                _LOGGER.debug("Connecting to %s", self.cli_args.wake_uri)
                wake_client = AsyncClient.from_uri(self.cli_args.wake_uri)

            async with mic_client, wake_client:
                _LOGGER.info("Detecting wake word")

                if self.cli_args.wake_word_name:
                    # Request specific wake word(s)
                    detect_event = Detect(names=self.cli_args.wake_word_name).event()
                else:
                    detect_event = Detect().event()

                await wake_client.write_event(detect_event)
                await self.forward_event(detect_event)
                _LOGGER.debug(detect_event)

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
                            mic_event = self._process_audio(mic_event)

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

    def _process_audio(self, audio_event: Event) -> Event:
        """Perform audio processing."""
        if not self.has_audio_processing:
            # No processing needed
            return audio_event

        chunk = AudioChunk.from_event(audio_event)
        audio_bytes = chunk.audio

        if self.process_webrtc is not None:
            audio_bytes = self.process_webrtc(audio_bytes)

        if self.volume_multiplier != 1.0:
            audio_bytes = multiply_volume(audio_bytes, self.volume_multiplier)

        return AudioChunk(
            rate=chunk.rate,
            width=chunk.width,
            channels=chunk.channels,
            audio=audio_bytes,
        ).event()

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
        # pylint: disable=consider-using-f-string
        ["{:02x}".format((uuid.getnode() >> ele) & 0xFF) for ele in range(0, 8 * 6, 8)][
            ::-1
        ]
    )


def needs_webrtc(args: argparse.Namespace) -> bool:
    """Return True if webrtc must be used."""
    return (
        (args.noise_suppression > 0) or (args.auto_gain > 0) or (args.vad == "webrtc")
    )


def needs_silero(args: argparse.Namespace) -> bool:
    """Return True if silero-vad must be used."""
    return args.vad == "silero"


class WebRtcAudio:
    _sub_chunk_samples: Final = 160
    _sub_chunk_bytes: Final = _sub_chunk_samples * 2  # 16-bit

    def __init__(self, auto_gain: int, noise_suppression: int) -> None:
        from webrtc_noise_gain import AudioProcessor

        self.audio_processor = AudioProcessor(auto_gain, noise_suppression)
        self.audio_buffer = AudioBuffer(self._sub_chunk_bytes)

    def __call__(self, audio_bytes: bytes) -> bytes:
        clean_chunk = bytes()
        for sub_chunk in chunk_samples(
            audio_bytes, self._sub_chunk_bytes, self.audio_buffer
        ):
            result = self.audio_processor.Process10ms(sub_chunk)
            clean_chunk += result.audio

        return clean_chunk


# -----------------------------------------------------------------------------

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
