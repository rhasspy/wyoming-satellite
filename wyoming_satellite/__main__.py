#!/usr/bin/env python3
import argparse
import asyncio
import logging
import math
import shlex
import sys
import time
import uuid
import wave
from enum import Enum
from functools import partial
from pathlib import Path
from typing import Callable, Final, Iterator, Optional, Union

from pyring_buffer import RingBuffer
from wyoming.asr import Transcribe, Transcript
from wyoming.audio import AudioChunk, AudioStart, AudioStop
from wyoming.client import AsyncClient
from wyoming.error import Error
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
    VAD_RESET = "vad-reset"
    VAD_WAIT = "vad-wait"
    PLAYING_AUDIO = "playing-audio"


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
    parser.add_argument("--vad-buffer-seconds", type=float, default=1)

    # Audio enhancement (requires webrtc-noise-audio)
    parser.add_argument(
        "--noise-suppression", type=int, default=0, choices=(0, 1, 2, 3, 4)
    )
    parser.add_argument("--auto-gain", type=int, default=0, choices=list(range(32)))

    # External event handlers
    parser.add_argument(
        "--event-uri", help="URI of Wyoming service to forward events to"
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

    # Sounds
    parser.add_argument(
        "--awake-wav", help="WAV file to play when wake word is detected"
    )
    parser.add_argument(
        "--done-wav", help="WAV file to play when voice command is done"
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

        self.is_running = True
        self.state: Optional[Satellite] = None
        self.after_tts_state: Optional[Satellite] = None
        self.satellite_task: Optional[asyncio.Task] = None

        self.mic_volume_multiplier = self.cli_args.mic_volume_multiplier
        self.has_mic_audio_processing = needs_webrtc(self.cli_args) or (
            self.mic_volume_multiplier != 1.0
        )
        self.process_webrtc: Optional[Callable[[bytes], bytes]] = None
        if needs_webrtc(self.cli_args):
            self.process_webrtc = WebRtcAudio(
                self.cli_args.auto_gain, self.cli_args.noise_suppression
            )

        self.has_wake = bool(self.cli_args.wake_uri or self.cli_args.wake_command)

        self.has_snd = bool(self.cli_args.snd_uri or self.cli_args.snd_command)
        self.snd_client: Optional[AsyncClient] = None
        self.snd_volume_multiplier = self.cli_args.snd_volume_multiplier
        self.has_snd_audio_processing = self.snd_volume_multiplier != 1.0

        self.process_vad: Optional[Callable[[Optional[bytes]], bool]] = None
        self.vad_buffer: Optional[RingBuffer] = None
        if needs_silero(self.cli_args):
            self.process_vad = SileroVad(
                self.cli_args.vad_threshold, self.cli_args.vad_trigger_level
            )
            if self.cli_args.vad_buffer_seconds > 0:
                # Assume 16Khz, 16-bit mono samples
                vad_buffer_bytes = int(
                    math.ceil(self.cli_args.vad_buffer_seconds * 16000 * 2)
                )
                self.vad_buffer = RingBuffer(vad_buffer_bytes)

        self.events_client: Optional[AsyncClient] = None

        _LOGGER.debug("Client connected: %s", self.client_id)

    # -------------------------------------------------------------------------

    async def handle_event(self, event: Event) -> bool:
        """Handle events from the server."""
        if Describe.is_type(event.type):
            await self.write_event(self.wyoming_info_event)
            _LOGGER.debug("Sent info to client: %s", self.client_id)
            return True

        if RunSatellite.is_type(event.type) and (self.satellite_task is None):
            self.after_tts_state = None

            if self.has_wake:
                # Local wake word detection
                self.state = SatelliteState.WAKE
                self.satellite_task = asyncio.create_task(self.run_satellite_wake())
            else:
                # Remote wake word detection
                self.state = SatelliteState.VAD_RESET
                self.satellite_task = asyncio.create_task(self.run_satellite())
        elif Transcript.is_type(event.type):
            if self.cli_args.done_wav:
                self.state = SatelliteState.PLAYING_AUDIO
                await self._play_wav(self.cli_args.done_wav)

            if self.has_wake:
                # Ready for next wake word detection
                self.state = SatelliteState.WAKE
                _LOGGER.info("Detecting wake word")
            else:
                self.state = SatelliteState.VAD_RESET

            # STT transcript
            await self._forward_event(event)
            _LOGGER.debug(event)
        elif self.has_snd and (
            AudioStart.is_type(event.type)
            or AudioChunk.is_type(event.type)
            or AudioStop.is_type(event.type)
        ):
            if AudioStart.is_type(event.type):
                # TTS start
                await self._ensure_snd_client()
                if self.snd_client is not None:
                    await self.snd_client.connect()

                    # State will be restored when audio ends
                    self.after_tts_state = self.state
                    self.state = SatelliteState.PLAYING_AUDIO

                await self._forward_event(event)
                _LOGGER.debug(event)
            elif AudioChunk.is_type(event.type) and (self.snd_client is not None):
                # Forward to sound service
                event = self._process_snd_audio(event)
                await self.snd_client.write_event(event)
            elif AudioStop.is_type(event.type):
                # TTS stop
                await self._forward_event(event)
                _LOGGER.debug(event)

                if self.snd_client is not None:
                    await self.snd_client.disconnect()
                    self.snd_client = None

                if self.after_tts_state is not None:
                    # Restore state after playing audio
                    self.state = self.after_tts_state
                    self.after_tts_state = None
        elif Detection.is_type(event.type):
            if self.cli_args.awake_wav:
                last_state = self.state
                self.state = SatelliteState.PLAYING_AUDIO
                await self._play_wav(self.cli_args.awake_wav)
                self.state = last_state

            await self._forward_event(event)
            _LOGGER.debug(event)
        elif (
            Detect.is_type(event.type)
            or Transcribe.is_type(event.type)
            or VoiceStarted.is_type(event.type)
            or VoiceStopped.is_type(event.type)
            or Synthesize.is_type(event.type)
        ):
            # Other client events:
            # - Detect for start of wake word detection
            # - Transcribe for when STT starts
            # - VoiceStarted/VoiceStopped for when user starts/stops speaking
            # - Synthesize for TTS text
            await self._forward_event(event)
            _LOGGER.debug(event)
        elif Error.is_type(event.type):
            await self._forward_event(event)
            _LOGGER.warning(event)
        else:
            _LOGGER.debug("Unexpected event: type=%s, data=%s", event.type, event.data)

        return True

    async def disconnect(self) -> None:
        self.is_running = False

    # -------------------------------------------------------------------------
    # Tasks
    # -------------------------------------------------------------------------

    async def run_satellite(self) -> None:
        """Task to read mic input and do remote wake word detection."""
        try:
            mic_client = self._make_mic_client()
            async with mic_client:
                while True:
                    mic_event = await mic_client.read_event()
                    if mic_event is None:
                        _LOGGER.warning("Microphone service disconnected")
                        break

                    if not AudioChunk.is_type(mic_event.type):
                        continue

                    mic_event = self._process_mic_audio(mic_event)

                    if self.state == SatelliteState.VAD_RESET:
                        # Reset vad state
                        if self.process_vad is not None:
                            self.process_vad(None)

                        if self.vad_buffer is not None:
                            self.vad_buffer.put(bytes(self.vad_buffer.maxlen))

                        self.state = SatelliteState.VAD_WAIT

                    if self.state == SatelliteState.VAD_WAIT:
                        if self.process_vad is None:
                            # No VAD
                            self.state = SatelliteState.ASR
                            _LOGGER.info("Streaming audio")

                            # Start pipeline
                            await self._run_pipeline(PipelineStage.WAKE)
                        else:
                            # Wait for speech
                            chunk = AudioChunk.from_event(mic_event)
                            if self.process_vad(chunk.audio):
                                # Ready to stream
                                self.state = SatelliteState.ASR

                                # Start pipeline
                                await self._run_pipeline(PipelineStage.WAKE)

                                if self.vad_buffer:
                                    # Send contents of VAD buffer first
                                    await self.write_event(
                                        AudioChunk(
                                            rate=chunk.rate,
                                            width=chunk.width,
                                            channels=chunk.channels,
                                            audio=self.vad_buffer.getvalue(),
                                        ).event()
                                    )

                                _LOGGER.info("Streaming audio")
                            elif self.vad_buffer is not None:
                                # Save audio right before speech
                                self.vad_buffer.put(chunk.audio)

                    if self.state == SatelliteState.ASR:
                        # Forward all audio to server
                        await self.write_event(mic_event)

        except ConnectionResetError:
            _LOGGER.info("Server disconnected")
        except Exception:
            _LOGGER.exception("Unexpected error in run_satellite")

    async def run_satellite_wake(self) -> None:
        """Task to read mic input and do local wake word detection."""
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
                await self._forward_event(detect_event)
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
                            mic_event = self._process_mic_audio(mic_event)

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

                            if self.cli_args.awake_wav:
                                self.state = SatelliteState.PLAYING_AUDIO
                                await self._play_wav(self.cli_args.awake_wav)

                            self.state = SatelliteState.ASR

                            # Start pipeline
                            await self._run_pipeline(PipelineStage.ASR)

                            # Forward to server
                            await self.write_event(wake_event)

                            # Forward to client
                            await self._forward_event(wake_event)

                            _LOGGER.info("Streaming audio")

                        # Next wake event
                        wake_task = asyncio.create_task(wake_client.read_event())
                        pending.add(wake_task)
        except ConnectionResetError:
            _LOGGER.info("Server disconnected")
        except Exception:
            _LOGGER.exception("Unexpected error in run_satellite")

    # -------------------------------------------------------------------------

    def _make_mic_client(self) -> AsyncClient:
        """Create mic client."""
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

    async def _ensure_snd_client(self) -> None:
        """Create snd client if necessary."""
        if (not self.has_snd) or (self.snd_client is not None):
            return

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

    async def _run_pipeline(self, start_stage: PipelineStage) -> None:
        """Tell server to start running the pipeline."""
        await self.write_event(
            RunPipeline(
                start_stage=start_stage,
                end_stage=PipelineStage.TTS if self.has_snd else PipelineStage.HANDLE,
                name=self.cli_args.pipeline,
            ).event()
        )

        if self.cli_args.streaming_start_command:
            await self._run_event_command(self.cli_args.streaming_start_command)

    def _process_mic_audio(self, audio_event: Event) -> Event:
        """Perform microphone audio processing, if necessary."""
        if not self.has_mic_audio_processing:
            # No processing needed
            return audio_event

        chunk = AudioChunk.from_event(audio_event)
        audio_bytes = chunk.audio

        if self.process_webrtc is not None:
            audio_bytes = self.process_webrtc(audio_bytes)

        if self.mic_volume_multiplier != 1.0:
            audio_bytes = multiply_volume(audio_bytes, self.mic_volume_multiplier)

        return AudioChunk(
            rate=chunk.rate,
            width=chunk.width,
            channels=chunk.channels,
            audio=audio_bytes,
        ).event()

    def _process_snd_audio(self, audio_event: Event) -> Event:
        """Perform output audio processing, if necessary."""
        if not self.has_snd_audio_processing:
            # No processing needed
            return audio_event

        chunk = AudioChunk.from_event(audio_event)
        audio_bytes = chunk.audio

        if self.snd_volume_multiplier != 1.0:
            audio_bytes = multiply_volume(audio_bytes, self.snd_volume_multiplier)

        return AudioChunk(
            rate=chunk.rate,
            width=chunk.width,
            channels=chunk.channels,
            audio=audio_bytes,
        ).event()

    async def _forward_event(self, event: Event) -> None:
        """Forward a Wyoming event to a client and run event commands."""
        if self.cli_args.detection_command and Detection.is_type(event.type):
            # Wake word is detected
            detection = Detection.from_event(event)
            await self._run_event_command(
                self.cli_args.detection_command, detection.name
            )
        elif self.cli_args.transcript_command and Transcript.is_type(event.type):
            # STT text is available
            transcript = Transcript.from_event(event)
            await self._run_event_command(
                self.cli_args.transcript_command, transcript.text
            )
        elif self.cli_args.stt_start_command and VoiceStarted.is_type(event.type):
            # User starts speaking
            await self._run_event_command(self.cli_args.stt_start_command)
        elif self.cli_args.stt_stop_command and VoiceStopped.is_type(event.type):
            # User stops speaking
            await self._run_event_command(self.cli_args.stt_stop_command)
        elif self.cli_args.synthesize_command and Synthesize.is_type(event.type):
            # TTS text is available
            synthesize = Synthesize.from_event(event)
            await self._run_event_command(
                self.cli_args.synthesize_command, synthesize.text
            )
        elif self.cli_args.tts_start_command and AudioStart.is_type(event.type):
            # TTS audio start
            await self._run_event_command(self.cli_args.tts_start_command)
        elif self.cli_args.tts_stop_command and AudioStop.is_type(event.type):
            # TTS audio stop
            await self._run_event_command(self.cli_args.tts_stop_command)

        if not self.cli_args.event_uri:
            # No external service
            return

        if self.events_client is None:
            self.events_client = AsyncClient.from_uri(self.cli_args.event_uri)
            _LOGGER.debug("Connecting to %s", self.cli_args.event_uri)
            await self.events_client.connect()

        assert self.events_client is not None
        await self.events_client.write_event(event)

    async def _run_event_command(
        self, command: str, command_input: Optional[str] = None
    ) -> None:
        """Run a custom event command with optional input."""
        _LOGGER.debug("Running %s", command)
        program, *program_args = shlex.split(command)
        proc = await asyncio.create_subprocess_exec(
            program, *program_args, stdin=asyncio.subprocess.PIPE
        )
        assert proc.stdin is not None

        if command_input:
            await proc.communicate(input=command_input.encode("utf-8"))
        else:
            proc.stdin.close()
            await proc.wait()

    async def _play_wav(self, wav_path: Union[str, Path]) -> None:
        """Send WAV file to snd client as audio chunks."""
        await self._ensure_snd_client()

        if self.snd_client is None:
            _LOGGER.debug("Cannot play WAV, no snd service")
            return

        try:
            async with self.snd_client:
                for event in self._wav_to_events(wav_path):
                    await self.snd_client.write_event(event)
        except Exception:
            _LOGGER.exception("Unexpected error while playing WAV: %s", wav_path)
        finally:
            self.snd_client = None

    def _wav_to_events(
        self, wav_path: Union[str, Path], samples_per_chunk: int = 1024
    ) -> Iterator[Event]:
        """Load WAV audio for playback on an event (wake/done)."""
        with wave.open(str(wav_path), "rb") as wav_file:
            rate = wav_file.getframerate()
            width = wav_file.getsampwidth()
            channels = wav_file.getnchannels()

            timestamp = 0
            yield AudioStart(
                rate=rate, width=width, channels=channels, timestamp=timestamp
            ).event()

            audio_bytes = wav_file.readframes(samples_per_chunk)
            while audio_bytes:
                if self.snd_volume_multiplier != 1.0:
                    audio_bytes = multiply_volume(
                        audio_bytes, self.snd_volume_multiplier
                    )

                chunk = AudioChunk(
                    rate=rate,
                    width=width,
                    channels=channels,
                    audio=audio_bytes,
                    timestamp=timestamp,
                )
                yield chunk.event()
                timestamp += int(chunk.seconds * 1000)
                audio_bytes = wav_file.readframes(samples_per_chunk)

            yield AudioStop(timestamp=timestamp).event()


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
    return (args.noise_suppression > 0) or (args.auto_gain > 0)


def needs_silero(args: argparse.Namespace) -> bool:
    """Return True if silero-vad must be used."""
    return args.vad


class WebRtcAudio:
    """Audio processing using webrtc."""

    _sub_chunk_samples: Final = 160  # 10ms @ 16Khz
    _sub_chunk_bytes: Final = _sub_chunk_samples * 2  # 16-bit

    def __init__(self, auto_gain: int, noise_suppression: int) -> None:
        from webrtc_noise_gain import AudioProcessor

        self.audio_processor = AudioProcessor(auto_gain, noise_suppression)
        self.audio_buffer = AudioBuffer(self._sub_chunk_bytes)

    def __call__(self, audio_bytes: bytes) -> bytes:
        """Process in 10ms chunks."""
        clean_chunk = bytes()
        for sub_chunk in chunk_samples(
            audio_bytes, self._sub_chunk_bytes, self.audio_buffer
        ):
            result = self.audio_processor.Process10ms(sub_chunk)
            clean_chunk += result.audio

        return clean_chunk


class SileroVad:
    """Voice activity detection with silero VAD."""

    def __init__(self, threshold: float, trigger_level: int) -> None:
        from pysilero_vad import SileroVoiceActivityDetector

        self.detector = SileroVoiceActivityDetector()
        self.threshold = threshold
        self.trigger_level = trigger_level
        self._activation = 0

    def __call__(self, audio_bytes: Optional[bytes]) -> bool:
        if audio_bytes is None:
            # Reset
            self._activation = 0
            return False

        if self.detector(audio_bytes) >= self.threshold:
            # Speech detected
            self._activation += 1
            if self._activation >= self.trigger_level:
                self._activation = 0
                return True
        else:
            # Silence detected
            self._activation = max(0, self._activation - 1)

        return False


# -----------------------------------------------------------------------------

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
