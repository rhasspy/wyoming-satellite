"""Main entry point for Wyoming satellite."""

import argparse
import asyncio
import logging
import sys
from functools import partial
from pathlib import Path

from wyoming.info import Attribution, Info, Satellite
from wyoming.server import AsyncServer, AsyncTcpServer

from . import __version__
from .event_handler import SatelliteEventHandler
from .satellite import (
    AlwaysStreamingSatellite,
    SatelliteBase,
    VadStreamingSatellite,
    WakeStreamingSatellite,
)
from .settings import (
    EventSettings,
    MicSettings,
    SatelliteSettings,
    SndSettings,
    TimerSettings,
    VadSettings,
    WakeSettings,
    WakeWordAndPipeline,
)
from .utils import (
    get_mac_address,
    needs_silero,
    needs_webrtc,
    run_event_command,
    split_command,
)

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
    parser.add_argument(
        "--mic-seconds-to-mute-after-awake-wav",
        type=float,
        default=0.5,
        help="Seconds to mute microphone after awake wav is finished playing (default: 0.5)",
    )
    parser.add_argument(
        "--mic-no-mute-during-awake-wav",
        action="store_true",
        help="Don't mute the microphone while awake wav is being played",
    )
    parser.add_argument(
        "--mic-channel-index",
        type=int,
        help="Take microphone input from a specific channel (first channel is 0)",
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
    parser.add_argument("--snd-volume-multiplier", type=float, default=1.0)

    # Local wake word detection
    parser.add_argument("--wake-uri", help="URI of Wyoming wake word detection service")
    parser.add_argument(
        "--wake-word-name",
        action="append",
        default=[],
        nargs="+",
        metavar=("name", "pipeline"),
        help="Name of wake word to listen for and optional pipeline name to run (requires --wake-uri)",
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
    parser.add_argument(
        "--wake-refractory-seconds",
        type=float,
        default=5.0,
        help="Seconds after a wake word detection before another detection is handled (default: 5)",
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
        "--tts-played-command",
        help="Command to run when text-to-speech audio stopped playing",
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
    parser.add_argument(
        "--connected-command",
        help="Command to run when connected to the server",
    )
    parser.add_argument(
        "--disconnected-command",
        help="Command to run when disconnected from the server",
    )
    parser.add_argument(
        "--timer-started-command",
        help="Command to run when a timer starts",
    )
    parser.add_argument(
        "--timer-updated-command",
        help="Command to run when a timer is paused, resumed, or has time added or removed",
    )
    parser.add_argument(
        "--timer-cancelled-command",
        "--timer-canceled-command",
        help="Command to run when a timer is cancelled",
    )
    parser.add_argument(
        "--timer-finished-command",
        help="Command to run when a timer finishes",
    )

    # Sounds
    parser.add_argument(
        "--awake-wav", help="WAV file to play when wake word is detected"
    )
    parser.add_argument(
        "--done-wav", help="WAV file to play when voice command is done"
    )
    parser.add_argument(
        "--timer-finished-wav", help="WAV file to play when a timer finishes"
    )
    parser.add_argument(
        "--timer-finished-wav-repeat",
        nargs=2,
        metavar=("repeat", "delay"),
        type=float,
        default=(1, 0),
        help="Number of times to play timer finished WAV and delay between repeats in seconds",
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
    parser.add_argument(
        "--debug-recording-dir", help="Directory to store audio for debugging"
    )
    parser.add_argument("--debug", action="store_true", help="Log DEBUG messages")
    parser.add_argument(
        "--log-format", default=logging.BASIC_FORMAT, help="Format for log messages"
    )
    parser.add_argument(
        "--version",
        action="version",
        version=__version__,
        help="Print version and exit",
    )
    args = parser.parse_args()

    # Validate args
    if (not args.mic_uri) and (not args.mic_command):
        _LOGGER.fatal("Either --mic-uri or --mic-command is required")
        sys.exit(1)

    if needs_webrtc(args):
        try:
            import webrtc_noise_gain  # noqa: F401
        except ImportError:
            _LOGGER.exception("Extras for webrtc are not installed")
            sys.exit(1)

    if needs_silero(args):
        try:
            import pysilero_vad  # noqa: F401
        except ImportError:
            _LOGGER.exception("Extras for silerovad are not installed")
            sys.exit(1)

    if args.awake_wav and (not Path(args.awake_wav).is_file()):
        _LOGGER.fatal("%s does not exist", args.awake_wav)
        sys.exit(1)

    if args.done_wav and (not Path(args.done_wav).is_file()):
        _LOGGER.fatal("%s does not exist", args.done_wav)
        sys.exit(1)

    if args.timer_finished_wav and (not Path(args.timer_finished_wav).is_file()):
        _LOGGER.fatal("%s does not exist", args.timer_finished_wav)
        sys.exit(1)

    if args.vad and (args.wake_uri or args.wake_command):
        _LOGGER.warning("VAD is not used with local wake word detection")

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO, format=args.log_format
    )
    _LOGGER.debug(args)

    if args.debug_recording_dir:
        args.debug_recording_dir = Path(args.debug_recording_dir)
        _LOGGER.info("Recording audio to %s", args.debug_recording_dir)

    wyoming_info = Info(
        satellite=Satellite(
            name=args.name,
            area=args.area,
            description=args.name,
            attribution=Attribution(name="", url=""),
            installed=True,
            version=__version__,
        )
    )

    settings = SatelliteSettings(
        mic=MicSettings(
            uri=args.mic_uri,
            command=split_command(args.mic_command),
            rate=args.mic_command_rate,
            width=args.mic_command_width,
            channels=args.mic_command_channels,
            samples_per_chunk=args.mic_command_samples_per_chunk,
            volume_multiplier=args.mic_volume_multiplier,
            auto_gain=args.mic_auto_gain,
            noise_suppression=args.mic_noise_suppression,
            seconds_to_mute_after_awake_wav=args.mic_seconds_to_mute_after_awake_wav,
            mute_during_awake_wav=(not args.mic_no_mute_during_awake_wav),
            channel_index=args.mic_channel_index,
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
            command=split_command(args.wake_command),
            names=[
                WakeWordAndPipeline(*wake_name) for wake_name in args.wake_word_name
            ],
            refractory_seconds=(
                args.wake_refractory_seconds
                if args.wake_refractory_seconds > 0
                else None
            ),
        ),
        snd=SndSettings(
            uri=args.snd_uri,
            command=split_command(args.snd_command),
            rate=args.snd_command_rate,
            width=args.snd_command_width,
            channels=args.snd_command_channels,
            volume_multiplier=args.snd_volume_multiplier,
            awake_wav=args.awake_wav,
            done_wav=args.done_wav,
        ),
        event=EventSettings(
            uri=args.event_uri,
            startup=split_command(args.startup_command),
            streaming_start=split_command(args.streaming_start_command),
            streaming_stop=split_command(args.streaming_stop_command),
            detect=split_command(args.detect_command),
            detection=split_command(args.detection_command),
            played=split_command(args.tts_played_command),
            transcript=split_command(args.transcript_command),
            stt_start=split_command(args.stt_start_command),
            stt_stop=split_command(args.stt_stop_command),
            synthesize=split_command(args.synthesize_command),
            tts_start=split_command(args.tts_start_command),
            tts_stop=split_command(args.tts_stop_command),
            error=split_command(args.error_command),
            connected=split_command(args.connected_command),
            disconnected=split_command(args.disconnected_command),
        ),
        timer=TimerSettings(
            started=split_command(args.timer_started_command),
            updated=split_command(args.timer_updated_command),
            cancelled=split_command(args.timer_cancelled_command),
            finished=split_command(args.timer_finished_command),
            finished_wav=args.timer_finished_wav,
            finished_wav_plays=int(args.timer_finished_wav_repeat[0]),
            finished_wav_delay=args.timer_finished_wav_repeat[1],
        ),
        debug_recording_dir=args.debug_recording_dir,
    )

    satellite: SatelliteBase

    if settings.wake.enabled:
        # Local wake word detection
        satellite = WakeStreamingSatellite(settings)
    elif settings.vad.enabled:
        # Stream after speech
        satellite = VadStreamingSatellite(settings)
    else:
        # Stream all the time
        satellite = AlwaysStreamingSatellite(settings)

    if args.startup_command:
        await run_event_command(split_command(args.startup_command))

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

    satellite_task = asyncio.create_task(satellite.run(), name="satellite run")

    try:
        await server.run(partial(SatelliteEventHandler, wyoming_info, satellite, args))
    except KeyboardInterrupt:
        pass
    finally:
        await satellite.stop()
        await satellite_task


# -----------------------------------------------------------------------------


def run():
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    run()
