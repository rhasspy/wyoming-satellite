"""Satellite code."""
import asyncio
import logging
import math
import time
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path
from typing import Callable, List, Optional, Set, Union

from pyring_buffer import RingBuffer
from wyoming.asr import Transcript
from wyoming.audio import AudioChunk, AudioStart, AudioStop
from wyoming.client import AsyncClient, AsyncTcpClient
from wyoming.event import Event, async_read_event, async_write_event
from wyoming.mic import MicProcessAsyncClient
from wyoming.pipeline import PipelineStage, RunPipeline
from wyoming.satellite import RunSatellite
from wyoming.snd import SndProcessAsyncClient
from wyoming.wake import Detect, Detection, WakeProcessAsyncClient

from .settings import SatelliteSettings
from .utils import multiply_volume, run_event_command, wav_to_events
from .vad import SileroVad
from .webrtc import WebRtcAudio

_LOGGER = logging.getLogger()


class State(Enum):
    NOT_STARTED = auto()
    STARTING = auto()
    STARTED = auto()
    RESTARTING = auto()
    STOPPING = auto()
    STOPPED = auto()


# -----------------------------------------------------------------------------


class SatelliteBase:
    def __init__(self, settings: SatelliteSettings) -> None:
        self.settings = settings
        self.server_id: Optional[str] = None
        self._state = State.NOT_STARTED
        self._state_changed = asyncio.Event()
        self._writer: Optional[asyncio.StreamWriter] = None

        self._mic_task: Optional[asyncio.Task] = None
        self._mic_webrtc: Optional[Callable[[bytes], bytes]] = None
        self._snd_task: Optional[asyncio.Task] = None
        self._snd_queue: "Optional[asyncio.Queue[Event]]" = None
        self._wake_task: Optional[asyncio.Task] = None
        self._wake_queue: "Optional[asyncio.Queue[Event]]" = None

    @property
    def is_running(self) -> bool:
        return self._state not in (State.STOPPING, State.STOPPED)

    @property
    def state(self) -> State:
        return self._state

    @state.setter
    def state(self, value: State) -> None:
        self._state = value
        self._state_changed.set()
        self._state_changed.clear()

    async def run(self) -> None:

        while self.is_running:
            try:
                if self.state == State.NOT_STARTED:
                    await self._start()
                elif self.state == State.RESTARTING:
                    await self._restart()
                elif self.state == State.STOPPING:
                    await self._stop()
                elif self.state == State.STOPPED:
                    await self.stopped()
                    break
                else:
                    await self._state_changed.wait()
            except Exception:
                if self.is_running:
                    # Automatically restart
                    _LOGGER.exception("Unexpected error running satellite")
                    self.state = State.RESTARTING

    async def _start(self) -> None:
        self.state = State.STARTING
        await self._connect_to_services()
        self.state = State.STARTED
        await self.started()

    async def started(self) -> None:
        pass

    async def _stop(self) -> None:
        self.server_id = None
        self._writer = None

        await self._disconnect_from_services()
        self.state = State.STOPPED

    async def stop(self) -> None:
        self.state = State.STOPPING

        # Wait for STOPPED
        while self.state != State.STOPPED:
            await self._state_changed.wait()

    async def stopped(self) -> None:
        pass

    def set_server(self, server_id: str, writer: asyncio.StreamWriter) -> None:
        self.server_id = server_id
        self._writer = writer

    async def event_from_server(self, event: Event) -> None:
        """Called when an event is received from the server."""
        if RunSatellite.is_type(event.type):
            if self.settings.wake.enabled:
                # Local wake word detection
                start_stage = PipelineStage.ASR
            else:
                # Remote wake word detection
                start_stage = PipelineStage.WAKE

            if self.settings.snd.enabled:
                # Play TTS response
                end_stage = PipelineStage.TTS
            else:
                # No audio output
                end_stage = PipelineStage.INTENT

            await self.event_to_server(
                RunPipeline(start_stage=start_stage, end_stage=end_stage).event()
            )
        elif (
            AudioChunk.is_type(event.type)
            or AudioStart.is_type(event.type)
            or AudioStop.is_type(event.type)
        ):
            # Forward to sound service
            await self.event_to_snd(event)

    async def event_to_server(self, event: Event) -> None:
        """Send an event to the server."""
        if self._writer is None:
            return

        await async_write_event(event, self._writer)

    async def event_to_snd(self, event: Event) -> None:
        """Send an event to the sound service."""
        if self._snd_queue is not None:
            self._snd_queue.put_nowait(event)

    async def _restart(self) -> None:
        self.state = State.RESTARTING
        await self._disconnect_from_services()

        _LOGGER.debug("Restarting in %s second(s)", self.settings.restart_timeout)
        await asyncio.sleep(self.settings.restart_timeout)
        self.state = State.NOT_STARTED

    async def _connect_to_services(self) -> None:
        if self.settings.mic.enabled:
            _LOGGER.debug(
                "Connecting to mic service: %s",
                self.settings.mic.uri or self.settings.mic.command,
            )
            self._mic_task = asyncio.create_task(self._mic_task_proc())

        if self.settings.snd.enabled:
            _LOGGER.debug(
                "Connecting to snd service: %s",
                self.settings.snd.uri or self.settings.snd.command,
            )
            self._snd_task = asyncio.create_task(self._snd_task_proc())

        if self.settings.wake.enabled:
            _LOGGER.debug(
                "Connecting to wake service: %s",
                self.settings.wake.uri or self.settings.wake.command,
            )
            self._wake_task = asyncio.create_task(self._wake_task_proc())

        _LOGGER.info("Connected to services")

    async def _disconnect_from_services(self) -> None:
        if self._mic_task is not None:
            _LOGGER.debug("Stopping microphone")
            self._mic_task.cancel()
            self._mic_task = None

        if self._snd_task is not None:
            _LOGGER.debug("Stopping sound")
            self._snd_task.cancel()
            self._snd_task = None

        _LOGGER.debug("Disconnected from services")

    # -------------------------------------------------------------------------
    # Microphone
    # -------------------------------------------------------------------------

    async def event_from_mic(
        self, event: Event, audio_bytes: Optional[bytes] = None
    ) -> None:
        pass

    def _make_mic_client(self) -> Optional[AsyncClient]:
        if self.settings.mic.command:
            program, *program_args = self.settings.mic.command
            return MicProcessAsyncClient(
                rate=self.settings.mic.rate,
                width=self.settings.mic.width,
                channels=self.settings.mic.channels,
                samples_per_chunk=self.settings.mic.samples_per_chunk,
                program=program,
                program_args=program_args,
            )

        if self.settings.mic.uri:
            return AsyncClient.from_uri(self.settings.mic.uri)

        return None

    async def _mic_task_proc(self) -> None:
        mic_client: Optional[AsyncClient] = None
        audio_bytes: Optional[bytes] = None

        if self.settings.mic.needs_webrtc and (self._mic_webrtc is None):
            _LOGGER.debug("Using webrtc audio enhancements")
            self._mic_webrtc = WebRtcAudio(
                self.settings.mic.auto_gain, self.settings.mic.noise_suppression
            )

        async def _disconnect() -> None:
            try:
                if mic_client is not None:
                    await mic_client.disconnect()
            except Exception:
                pass  # ignore disconnect errors

        while self.is_running:
            try:
                if mic_client is None:
                    mic_client = self._make_mic_client()
                    assert mic_client is not None
                    await mic_client.connect()
                    _LOGGER.debug("Connected to mic service")

                event = await mic_client.read_event()
                if event is None:
                    _LOGGER.warning("Mic service disconnected")
                    await _disconnect()
                    mic_client = None  # reconnect
                    await asyncio.sleep(self.settings.mic.reconnect_seconds)
                    continue

                # Audio processing
                if self.settings.mic.needs_processing and AudioChunk.is_type(
                    event.type
                ):
                    chunk = AudioChunk.from_event(event)
                    audio_bytes = self._process_mic_audio(chunk.audio)
                    event = AudioChunk(
                        rate=chunk.rate,
                        width=chunk.width,
                        channels=chunk.channels,
                        audio=audio_bytes,
                    ).event()
                else:
                    audio_bytes = None

                await self.event_from_mic(event, audio_bytes)
            except asyncio.CancelledError:
                break
            except Exception:
                _LOGGER.exception("Unexpected error in mic read task")
                await _disconnect()
                mic_client = None  # reconnect
                await asyncio.sleep(self.settings.mic.reconnect_seconds)

        await _disconnect()

    def _process_mic_audio(self, audio_bytes: bytes) -> bytes:
        if self.settings.mic.volume_multiplier != 1.0:
            audio_bytes = multiply_volume(
                audio_bytes, self.settings.mic.volume_multiplier
            )

        if self._mic_webrtc is not None:
            audio_bytes = self._mic_webrtc(audio_bytes)

        return audio_bytes

    # -------------------------------------------------------------------------
    # Sound
    # -------------------------------------------------------------------------

    def _make_snd_client(self) -> Optional[AsyncClient]:
        if self.settings.snd.command:
            program, *program_args = self.settings.snd.command
            return SndProcessAsyncClient(
                rate=self.settings.snd.rate,
                width=self.settings.snd.width,
                channels=self.settings.snd.channels,
                program=program,
                program_args=program_args,
            )

        if self.settings.snd.uri:
            return AsyncClient.from_uri(self.settings.snd.uri)

        return None

    async def _snd_task_proc(self) -> None:
        snd_client: Optional[AsyncClient] = None

        async def _disconnect() -> None:
            try:
                if snd_client is not None:
                    await snd_client.disconnect()
            except Exception:
                pass  # ignore disconnect errors

        while self.is_running:
            try:
                if self._snd_queue is None:
                    self._snd_queue = asyncio.Queue()

                event = await self._snd_queue.get()

                if snd_client is None:
                    snd_client = self._make_snd_client()
                    assert snd_client is not None
                    await snd_client.connect()
                    _LOGGER.debug("Connected to snd service")

                # TODO: audio processing

                await snd_client.write_event(event)
            except asyncio.CancelledError:
                break
            except Exception:
                _LOGGER.exception("Unexpected error in snd read task")
                await _disconnect()
                snd_client = None  # reconnect
                self._snd_queue = None
                await asyncio.sleep(self.settings.snd.reconnect_seconds)

        await _disconnect()

    async def _play_wav(self, wav_path: Optional[Union[str, Path]]) -> None:
        """Send WAV as events to sound service."""
        if (not wav_path) or (not self.settings.snd.enabled):
            return

        for event in wav_to_events(
            wav_path,
            samples_per_chunk=self.settings.snd.samples_per_chunk,
            volume_multiplier=self.settings.snd.volume_multiplier,
        ):
            await self.event_to_snd(event)

    # -------------------------------------------------------------------------
    # Wake
    # -------------------------------------------------------------------------

    async def event_from_wake(self, event: Event) -> None:
        pass

    async def event_to_wake(self, event: Event) -> None:
        if self._wake_queue is not None:
            self._wake_queue.put_nowait(event)

    def _make_wake_client(self) -> Optional[AsyncClient]:
        if self.settings.wake.command:
            program, *program_args = self.settings.wake.command
            return WakeProcessAsyncClient(
                rate=self.settings.wake.rate,
                width=self.settings.wake.width,
                channels=self.settings.wake.channels,
                program=program,
                program_args=program_args,
            )

        if self.settings.wake.uri:
            return AsyncClient.from_uri(self.settings.wake.uri)

        return None

    async def _wake_task_proc(self) -> None:
        wake_client: Optional[AsyncClient] = None
        to_client_task: Optional[asyncio.Task] = None
        from_client_task: Optional[asyncio.Task] = None
        pending: Set[asyncio.Task] = set()

        async def _disconnect() -> None:
            try:
                if wake_client is not None:
                    await wake_client.disconnect()
            except Exception:
                pass  # ignore disconnect errors

        while self.is_running:
            try:
                if self._wake_queue is None:
                    self._wake_queue = asyncio.Queue()

                if wake_client is None:
                    wake_client = self._make_wake_client()
                    assert wake_client is not None
                    await wake_client.connect()
                    _LOGGER.debug("Connected to wake service")

                    # Reset
                    from_client_task = None
                    to_client_task = None
                    pending = set()
                    self._wake_queue = asyncio.Queue()

                    await self._send_wake_detect()

                if to_client_task is None:
                    # From satellite to wake service
                    to_client_task = asyncio.create_task(self._wake_queue.get())
                    pending.add(to_client_task)

                if from_client_task is None:
                    # From wake service to satellite
                    from_client_task = asyncio.create_task(wake_client.read_event())
                    pending.add(from_client_task)

                done, pending = await asyncio.wait(
                    pending, return_when=asyncio.FIRST_COMPLETED
                )

                if to_client_task in done:
                    assert to_client_task is not None
                    event = to_client_task.result()
                    to_client_task = None
                    await wake_client.write_event(event)

                if from_client_task in done:
                    assert from_client_task is not None
                    event = from_client_task.result()
                    from_client_task = None

                    if event is None:
                        _LOGGER.warning("Wake service disconnected")
                        await _disconnect()
                        wake_client = None  # reconnect
                        await asyncio.sleep(self.settings.wake.reconnect_seconds)
                        continue

                    # TODO: audio processing
                    await self.event_from_wake(event)

            except asyncio.CancelledError:
                break
            except Exception:
                _LOGGER.exception("Unexpected error in wake read task")
                await _disconnect()
                wake_client = None  # reconnect
                await asyncio.sleep(self.settings.wake.reconnect_seconds)

        await _disconnect()

    async def _send_wake_detect(self) -> None:
        """Inform wake word service of which wake words to detect."""
        await self.event_to_wake(Detect(names=self.settings.wake.names).event())
        await self.trigger_detect()

    # -------------------------------------------------------------------------
    # Events
    # -------------------------------------------------------------------------

    async def trigger_streaming_start(self) -> None:
        await run_event_command(self.settings.event.streaming_start)

    async def trigger_streaming_stop(self) -> None:
        await run_event_command(self.settings.event.streaming_stop)

    async def trigger_detect(self) -> None:
        await run_event_command(self.settings.event.detect)

    async def trigger_detection(self, detection: Detection) -> None:
        await run_event_command(self.settings.event.detection, detection.name)
        await self._play_wav(self.settings.snd.awake_wav)

    async def trigger_transcript(self, transcript: Transcript) -> None:
        await run_event_command(self.settings.event.transcript, transcript.text)
        await self._play_wav(self.settings.snd.done_wav)


# -----------------------------------------------------------------------------


class AlwaysStreamingSatellite(SatelliteBase):
    """Satellite that always streams audio."""

    def __init__(self, settings: SatelliteSettings) -> None:
        super().__init__(settings)
        self.is_streaming = False

    async def event_from_server(self, event: Event) -> None:
        await super().event_from_server(event)

        if RunSatellite.is_type(event.type):
            self.is_streaming = True
            _LOGGER.info("Streaming audio")
            await self.trigger_streaming_start()
        elif Detect.is_type(event.type):
            await self.trigger_detect()
        elif Detection.is_type(event.type):
            _LOGGER.debug("Wake word detected")
            await self.trigger_detection(Detection.from_event(event))
        elif Transcript.is_type(event.type):
            _LOGGER.debug(event)
            await self.trigger_transcript(Transcript.from_event(event))

    async def event_from_mic(
        self, event: Event, audio_bytes: Optional[bytes] = None
    ) -> None:
        if not self.is_streaming:
            return

        if AudioChunk.is_type(event.type):
            # Forward to server
            await self.event_to_server(event)


# -----------------------------------------------------------------------------


class VadStreamingSatellite(SatelliteBase):
    """Satellite that only streams after speech is detected."""

    def __init__(self, settings: SatelliteSettings) -> None:
        if not settings.vad.enabled:
            raise ValueError("VAD is not enabled")

        super().__init__(settings)
        self.is_streaming = False
        self.vad = SileroVad(
            threshold=settings.vad.threshold, trigger_level=settings.vad.trigger_level
        )
        self.timeout_seconds: Optional[float] = None
        self.vad_buffer: Optional[RingBuffer] = None

        if settings.vad.buffer_seconds > 0:
            # Assume 16Khz, 16-bit mono samples
            vad_buffer_bytes = int(math.ceil(settings.vad.buffer_seconds * 16000 * 2))
            self.vad_buffer = RingBuffer(maxlen=vad_buffer_bytes)

    async def event_from_server(self, event: Event) -> None:
        await super().event_from_server(event)

        if RunSatellite.is_type(event.type):
            _LOGGER.info("Waiting for speech")
        elif Detect.is_type(event.type):
            await self.trigger_detect()
        elif Detection.is_type(event.type):
            _LOGGER.debug("Wake word detected")
            await self.trigger_detection(Detection.from_event(event))
        elif Transcript.is_type(event.type):
            _LOGGER.debug(event)
            await self.trigger_transcript(Transcript.from_event(event))

    async def event_from_mic(
        self, event: Event, audio_bytes: Optional[bytes] = None
    ) -> None:
        if not AudioChunk.is_type(event.type):
            return

        if (
            self.is_streaming
            and (self.timeout_seconds is not None)
            and (time.monotonic() >= self.timeout_seconds)
        ):
            # Time out during wake word recognition
            self.is_streaming = False
            self.timeout_seconds = None

            # Stop pipeline
            await self.event_to_server(AudioStop().event())

            _LOGGER.info("Waiting for speech")
            await self.trigger_streaming_stop()

        if not self.is_streaming:
            # Check VAD
            if audio_bytes is None:
                # Need to unpack
                chunk = AudioChunk.from_event(event)
                audio_bytes = chunk.audio

            if not self.vad(audio_bytes):
                # No speech
                if self.vad_buffer is not None:
                    self.vad_buffer.put(audio_bytes)

                return

            # Speech detected
            self.is_streaming = True
            _LOGGER.info("Streaming audio")
            await self.trigger_streaming_start()

            if self.settings.vad.wake_word_timeout is not None:
                self.timeout_seconds = (
                    time.monotonic() + self.settings.vad.wake_word_timeout
                )
            else:
                self.timeout_seconds = None

            if self.vad_buffer is not None:
                # Send contents of VAD buffer first
                await self.event_to_server(
                    AudioChunk(
                        rate=chunk.rate,
                        width=chunk.width,
                        channels=chunk.channels,
                        audio=self.vad_buffer.getvalue(),
                    ).event()
                )

            self._reset_vad()

        if self.is_streaming:
            # Forward to server
            await self.event_to_server(event)

    def _reset_vad(self):
        self.vad(None)
        if self.vad_buffer is not None:
            self.vad_buffer.put(bytes(self.vad_buffer.maxlen))


# -----------------------------------------------------------------------------


class WakeStreamingSatellite(SatelliteBase):
    """Satellite that waits for local wake word detection before streaming."""

    def __init__(self, settings: SatelliteSettings) -> None:
        if not settings.wake.enabled:
            raise ValueError("Local wake word detection is not enabled")

        super().__init__(settings)
        self.is_streaming = False

    async def event_from_server(self, event: Event) -> None:
        await super().event_from_server(event)

        if RunSatellite.is_type(event.type) or Transcript.is_type(event.type):
            self.is_streaming = False
            await self._send_wake_detect()
            _LOGGER.info("Waiting for wake word")

            if Transcript.is_type(event.type):
                _LOGGER.debug(event)
                await self.trigger_streaming_stop()
                await self.trigger_transcript(Transcript.from_event(event))

    async def event_from_mic(
        self, event: Event, audio_bytes: Optional[bytes] = None
    ) -> None:
        if not AudioChunk.is_type(event.type):
            return

        if self.is_streaming:
            # Forward to server
            await self.event_to_server(event)
        else:
            # Forward to wake word service
            await self.event_to_wake(event)

    async def event_from_wake(self, event: Event) -> None:
        if self.is_streaming:
            return

        if Detection.is_type(event.type):
            self.is_streaming = True
            _LOGGER.debug("Streaming audio")
            await self.trigger_detection(Detection.from_event(event))
            await self.trigger_streaming_start()
