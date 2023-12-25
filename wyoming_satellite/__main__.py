#!/usr/bin/env python3
import argparse
import asyncio
import logging
import shlex
import sys
import time
import uuid
from functools import partial
from pathlib import Path
from typing import List, Optional

from wyoming.event import Event
from wyoming.info import Attribution, Describe, Info, Satellite
from wyoming.server import AsyncEventHandler, AsyncServer, AsyncTcpServer

from .satellite import (
    AlwaysStreamingSatellite,
    SatelliteBase,
    VadStreamingSatellite,
    WakeStreamingSatellite,
    WakeStreamingSatelliteWithVAD,
)
from .settings import (
    EventSettings,
    MicSettings,
    SatelliteSettings,
    SndSettings,
    VadSettings,
    WakeSettings,
)
from .utils import run_event_command

_LOGGER = logging.getLogger()
_DIR = Path(__file__).parent


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
    parser.add_argument("--mic-volume-multiplier", type=float, default=1.0)
    parser.add_argument(
        "--mic-noise-suppression", type=int, default=0, choices=(0, 1, 2, 3, 4)
    )
    parser.add_argument("--mic-auto-gain", type=int, default=0, choices=list(range(32)))

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
    parser.add_argument("--snd-volume-multiplier", type=float, default=1.0)

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
        "--vad", action="store_true", help="Wait for speech before streaming audio"
    )
    parser.add_argument("--vad-threshold", type=float, default=0.5)
    parser.add_argument("--vad-trigger-level", type=int, default=1)
    parser.add_argument("--vad-buffer-seconds", type=float, default=2)
    parser.add_argument(
        "--vad-wake-word-timeout",
        type=float,
        default=5.0,
        help="Seconds before going back to waiting for speech when wake word isn't detected",
    )

    # External event handlers
    parser.add_argument(
        "--event-uri", help="URI of Wyoming service to forward events to"
    )
    parser.add_argument(
        "--startup-command", help="Command run when the satellite starts"
    )
    parser.add_argument(
        "--detect-command", help="Command to run when wake word detection starts"
    )
    parser.add_argument(
        "--detection-command", help="Command to run when wake word is detected"
    )
    parser.add_argument(
        "--transcript-command",
        help="Command to run when speech to text transcript is returned",
    )
    parser.add_argument(
        "--stt-start-command",
        help="Command to run when the user starts speaking",
    )
    parser.add_argument(
        "--stt-stop-command",
        help="Command to run when the user stops speaking",
    )
    parser.add_argument(
        "--synthesize-command",
        help="Command to run when text to speech text is returned",
    )
    parser.add_argument(
        "--tts-start-command",
        help="Command to run when text to speech response starts",
    )
    parser.add_argument(
        "--tts-stop-command",
        help="Command to run when text to speech response stops",
    )
    parser.add_argument(
        "--streaming-start-command",
        help="Command to run when audio streaming starts",
    )
    parser.add_argument(
        "--streaming-stop-command",
        help="Command to run when audio streaming stops",
    )
    parser.add_argument(
        "--error-command",
        help="Command to run when an error occurs",
    )

    # Sounds
    parser.add_argument(
        "--awake-wav", help="WAV file to play when wake word is detected"
    )
    parser.add_argument(
        "--done-wav", help="WAV file to play when voice command is done"
    )

    # Satellite details
    parser.add_argument("--uri", required=True, help="unix:// or tcp://")
    parser.add_argument(
        "--name", default="Wyoming Satellite", help="Name of the satellite"
    )
    parser.add_argument("--area", help="Area name of the satellite")

    # Zeroconf
    parser.add_argument(
        "--no-zeroconf", action="store_true", help="Disable discovery over zeroconf"
    )
    parser.add_argument(
        "--zeroconf-name",
        help="Name used for zeroconf discovery (default: MAC from uuid.getnode)",
    )
    parser.add_argument(
        "--zeroconf-host",
        help="Host address for zeroconf discovery (default: detect)",
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
            _LOGGER.fatal("Install extras for silerovad")
            sys.exit(1)

    if args.awake_wav and (not Path(args.awake_wav).is_file()):
        _LOGGER.fatal("%s does not exist", args.awake_wav)
        sys.exit(1)

    if args.done_wav and (not Path(args.done_wav).is_file()):
        _LOGGER.fatal("%s does not exist", args.done_wav)
        sys.exit(1)

    if args.vad and (args.wake_uri or args.wake_command):
        _LOGGER.warning("VAD is not used with local wake word detection")

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

    settings = SatelliteSettings(
        mic=MicSettings(
            uri=args.mic_uri,
            command=_split(args.mic_command),
            rate=args.mic_command_rate,
            width=args.mic_command_width,
            channels=args.mic_command_channels,
            samples_per_chunk=args.mic_command_samples_per_chunk,
            volume_multiplier=args.mic_volume_multiplier,
            auto_gain=args.mic_auto_gain,
            noise_suppression=args.mic_noise_suppression,
        ),
        vad=VadSettings(
            enabled=args.vad,
            threshold=args.vad_threshold,
            trigger_level=args.vad_trigger_level,
            buffer_seconds=args.vad_buffer_seconds,
            wake_word_timeout=args.vad_wake_word_timeout,
        ),
        wake=WakeSettings(
            uri=args.wake_uri,
            command=_split(args.wake_command),
            names=args.wake_word_name,
        ),
        snd=SndSettings(
            uri=args.snd_uri,
            command=_split(args.snd_command),
            rate=args.snd_command_rate,
            width=args.snd_command_width,
            channels=args.snd_command_channels,
            volume_multiplier=args.snd_volume_multiplier,
            awake_wav=args.awake_wav,
            done_wav=args.done_wav,
        ),
        event=EventSettings(
            uri=args.event_uri,
            startup=_split(args.startup_command),
            streaming_start=_split(args.streaming_start_command),
            streaming_stop=_split(args.streaming_stop_command),
            detect=_split(args.detect_command),
            detection=_split(args.detection_command),
            transcript=_split(args.transcript_command),
            stt_start=_split(args.stt_start_command),
            stt_stop=_split(args.stt_stop_command),
            synthesize=_split(args.synthesize_command),
            tts_start=_split(args.tts_start_command),
            tts_stop=_split(args.tts_stop_command),
            error=_split(args.error_command),
        ),
    )

    satellite: SatelliteBase

    if settings.wake.enabled and settings.vad.enabled:
        # Local wake word detection with VAD
        satellite = WakeStreamingSatelliteWithVAD(settings)
    elif settings.wake.enabled:
        # Local wake word detection
        satellite = WakeStreamingSatellite(settings)
    elif settings.vad.enabled:
        # Stream after speech
        satellite = VadStreamingSatellite(settings)
    else:
        # Stream all the time
        satellite = AlwaysStreamingSatellite(settings)

    if args.startup_command:
        await run_event_command(_split(args.startup_command))

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
            host=args.zeroconf_host,
        )
        _LOGGER.debug(
            "Zeroconf discovery enabled (name=%s, host=%s)",
            args.zeroconf_name,
            args.zeroconf_host,
        )

    satellite_task = asyncio.create_task(satellite.run())

    try:
        await server.run(partial(SatelliteEventHandler, wyoming_info, satellite, args))
    except KeyboardInterrupt:
        pass
    finally:
        await satellite.stop()
        await satellite_task


# -----------------------------------------------------------------------------


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
        self.wyoming_info_event = wyoming_info.event()
        self.client_id = str(time.monotonic_ns())
        self.satellite = satellite

    # -------------------------------------------------------------------------

    async def handle_event(self, event: Event) -> bool:
        """Handle events from the server."""
        if Describe.is_type(event.type):
            await self.write_event(self.wyoming_info_event)
            return True

        if self.satellite.server_id is None:
            # Take over after a problem occurred
            self.satellite.set_server(self.client_id, self.writer)
        elif self.satellite.server_id != self.client_id:
            # New connection
            _LOGGER.debug("Connection cancelled: %s", self.client_id)
            return False

        await self.satellite.event_from_server(event)

        return True

    async def disconnect(self) -> None:
        """Server disconnect."""
        if self.satellite.server_id == self.client_id:
            self.satellite.clear_server()


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
    return (args.mic_noise_suppression > 0) or (args.mic_auto_gain > 0)


def needs_silero(args: argparse.Namespace) -> bool:
    """Return True if silero-vad must be used."""
    return args.vad


def _split(command: Optional[str]) -> Optional[List[str]]:
    if not command:
        return None

    return shlex.split(command)


# -----------------------------------------------------------------------------

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
