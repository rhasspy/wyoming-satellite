from enum import Enum, StrEnum, auto
import sys
import math
import logging
import time
import asyncio
from typing import (
    Any,
    Awaitable,
    Callable,
    ClassVar,
    Coroutine,
    Final,
    List,
    Mapping,
    Optional,
)
import queue

from pyring_buffer import RingBuffer


from wyoming.client import AsyncClient
from wyoming.info import Describe, Info
from wyoming.asr import Transcript
from wyoming.audio import AudioChunk, AudioStop, AudioStart, AudioFormat
from wyoming.error import Error
from wyoming.event import Event
from wyoming.satellite import (
    PauseSatellite,
    RunSatellite,
)
from wyoming.wake import Detection
from wyoming.snd import SndProcessAsyncClient

from .utils.audio import wav_to_events

from .satellite import SatelliteBase
from .settings import SatelliteSettings
from .vad import SileroVad


_LOGGER = logging.getLogger()
_WAKE_INFO_TIMEOUT: Final = 2


class SatState(Enum):
    """Nodes in the finite state machine graph"""

    PAUSED = auto()
    """The satellite is not listening. It is waiting for a connection or a start command from a server."""

    MONITOR = auto()
    """The satellite is listening, and forwarding audio to the wakeword service. It is waiting for a wakeword detection."""

    STREAM_TO_SERVER = auto()
    """The satellite is streaming mic audio to the server."""

    PLAYBACK = auto()
    """The satellite is playing audio from the server. In this state, the satellite does not process mic input."""

    FOLLOWUP = auto()
    """The satellite recently finished playback, and we are now waiting to see if the user responds. In this state, a wakeword is not required; the satellite will start streaming audio to the server again as soon as the VAD triggers. """


class SatEvent(StrEnum):
    """Events which affect the state of the satellite."""

    VAD = "vad"
    """The voice activation detection service triggered."""

    WAKEWORD = "wakeword"
    """The wakeword detection service triggered."""

    STATE_CHANGE = "state_change"
    """The satellite changed states."""

    TTS_START = "tts_start"
    """The satellite started playing audio from the server."""

    TTS_END = "tts_end"
    """The satellite stopped playing audio from the server."""

    SERVER_DISCONNECT = "server_disconnect"
    """The server disconnected."""

    SERVER_CONNECT = "server_connect"
    """The server connected."""

    PAUSE = "pause"
    """The server instructed the satellite to pause."""


StateChangeListener = Callable[
    ["FSMSatellite", SatState, SatState], Coroutine[Any, Any, None]
]
StateChangePredicate = Callable[[SatState, SatState], bool]


_state_change_listeners: list[tuple[StateChangePredicate, StateChangeListener]] = []


def on_state_change(
    old_state: Optional[SatState] = None,
    new_state: Optional[SatState] = None,
) -> Callable[[StateChangeListener], StateChangeListener]:
    """
    Decorator that registers a method as a state change listener. The method will be
    invoked when the satellite changes states. If old_state is provided, then the
    listener only triggers when the satellite is exiting the given state. Likewise,
    if new_state is provided, the listener triggers only when the satellite is
    entering new_state. Valid on instance methods of FSMSatellite.
    """

    def state_change_decorator(func: StateChangeListener) -> StateChangeListener:
        key = old_state, new_state

        def predicate(event_old_state: SatState, event_new_state: SatState) -> bool:
            if old_state is not None and old_state != event_old_state:
                return False
            if new_state is not None and new_state != event_new_state:
                return False
            return True

        _state_change_listeners.append((predicate, func))
        return func

    return state_change_decorator


class FSMSatellite(SatelliteBase):
    """
    A satellite that uses both wakeword and VAD to support back-and-forth conversation.
    A wakeword trigger is required for the first user speech, but for a short time
    after TTS plays, a wakeword is not required to stream a follow-up prompt.

    See SatState enum docs for full state machine details.
    """

    def __init__(self, settings: SatelliteSettings) -> None:
        super().__init__(settings)
        self.vad = SileroVad(
            threshold=settings.vad.threshold, trigger_level=settings.vad.trigger_level
        )
        self.mic_format: AudioFormat = AudioFormat(
            settings.mic.rate, settings.mic.width, settings.mic.channels
        )

        self.sat_events: dict[SatEvent, float] = {}
        self.sat_state: SatState = SatState.PAUSED
        self.wav_tasks: List[asyncio.Task] = []

        # Audio from right before speech starts (circular buffer)
        self.vad_buffer: Optional[RingBuffer] = None
        self.vad_chunk: Optional[AudioChunk] = None
        self.last_debug: float = time.monotonic()
        # track a heuristic for when we expect the TTS audio from the server to stop playing.
        # this is only a best-effort guess.
        self.expected_playback_end: float = time.monotonic()

        self._wake_info: Optional[Info] = None
        self._wake_info_ready = asyncio.Event()
        self._debug_recording_timestamp: Optional[int] = None

        if settings.vad.buffer_seconds > 0:
            vad_buffer_bytes = int(
                math.ceil(
                    settings.vad.buffer_seconds
                    * self.mic_format.rate
                    * self.mic_format.width
                    * self.mic_format.channels
                )
            )
            self.vad_buffer = RingBuffer(maxlen=vad_buffer_bytes)

    async def run(self) -> None:
        async with asyncio.TaskGroup() as tg:
            tg.create_task(super().run())
            tg.create_task(self.background_tasks())

    async def background_tasks(self) -> None:
        """Asynchronously read from stdin. When a line is read, print debug info on the current state."""
        lines: queue.Queue[str] = queue.Queue()

        def read_stdin() -> str:
            return sys.stdin.readline()

        while True:
            line = await asyncio.to_thread(read_stdin)
            t_since = {e.name: self.time_since_last_event(e) for e in self.sat_events}
            _LOGGER.debug(f"current status: {self.sat_state} {t_since}")

    def mark_sat_event(self, event: SatEvent) -> None:
        """Record the time when an event occurs, overwriting previous occurrences."""
        self.sat_events[event] = time.monotonic()

    def times_since_events(self) -> Mapping[SatEvent, float | None]:
        """
        Return a mapping from all sat events that happened since the
        last state change, to the number of seconds since that event occurred.
        """
        now = time.monotonic()
        return {e: self.time_since_last_event(e, now) for e in self.sat_events}

    def set_sat_state(self, new_state: SatState) -> None:
        """
        Update the satellite state, reseting all sat events.
        """
        old_state = self.sat_state
        if old_state == new_state:
            _LOGGER.warning(
                f"Tried to change state, but we were already in the requested state {new_state}. Ignoring."
            )
            return
        _LOGGER.debug(
            f"exiting state: {old_state}  events: {self.times_since_events()}"
        )
        _LOGGER.info(f"entering state: {new_state}")
        self.sat_state = new_state
        self.sat_events = {}
        self.mark_sat_event(SatEvent.STATE_CHANGE)

    async def play_wav_background(self, wav_path: str) -> None:
        """
        Play a wav file asynchronously.
        """

        async def background_task() -> None:
            client = self._make_snd_client()
            assert client is not None
            await client.connect()
            try:
                for event in wav_to_events(
                    wav_path,
                    samples_per_chunk=self.settings.snd.samples_per_chunk,
                ):
                    await client.write_event(event)
            finally:
                await client.disconnect()

        i: int = 0
        while i < len(self.wav_tasks):
            task = self.wav_tasks[i]
            if task.done():
                await self.wav_tasks.pop(i)
            else:
                i += 1
        self.wav_tasks.append(asyncio.create_task(background_task()))

    async def event_from_server(self, event: Event) -> None:
        await super().event_from_server(event)

        if RunSatellite.is_type(event.type):
            _LOGGER.info("server requested satellite start; starting")
            if self.sat_state == SatState.PAUSED:
                self.set_sat_state(SatState.MONITOR)
        elif Detection.is_type(event.type):
            # Start debug recording
            if self.stt_audio_writer is not None:
                self.stt_audio_writer.start()
        elif (
            Transcript.is_type(event.type)
            or Error.is_type(event.type)
            or PauseSatellite.is_type(event.type)
        ):
            if PauseSatellite.is_type(event.type):
                self.mark_sat_event(SatEvent.PAUSE)
            # Stop debug recording
            if self.stt_audio_writer is not None:
                self.stt_audio_writer.stop()

    async def event_from_mic(
        self, event: Event, audio_bytes: Optional[bytes] = None
    ) -> None:
        if (
            (not AudioChunk.is_type(event.type))
            or self.microphone_muted
            or self.sat_state == SatState.PAUSED
        ):
            return
        chunk = AudioChunk.from_event(event)
        audio_bytes = chunk.audio
        now = time.monotonic()
        if now - self.last_debug > 1:
            self.last_debug = now

        if self.stt_audio_writer is not None and audio_bytes is not None:
            self.stt_audio_writer.write(audio_bytes)

        voice_detected = self.vad(audio_bytes)
        if voice_detected:
            self.mark_sat_event(SatEvent.VAD)

        new_state = await self.update_state()

        await self.event_to_wake(event)
        if new_state == SatState.STREAM_TO_SERVER:
            await self.event_to_server(event)
        if new_state in (SatState.MONITOR, SatState.FOLLOWUP):
            if self.vad_buffer is not None:
                self.vad_chunk = chunk
                self.vad_buffer.put(audio_bytes)

    async def update_state(self) -> SatState:
        """
        Check if a state transition should happen. If so, update our state
        and trigger appropriate listeners.

        :returns: The current satellite state, which may or may not differ
            from the old state.
        """
        old_state = self.sat_state
        new_state = self.get_next_state()
        if old_state != new_state:
            self.set_sat_state(new_state)
            await self.handle_state_change(old_state, new_state)
        return new_state

    @on_state_change(new_state=SatState.STREAM_TO_SERVER)
    async def on_stream_start(self, old_state: SatState, new_state: SatState) -> None:
        """
        When we are about to start streaming audio to the server, send the server
        audio and pipeline start events, then send any buffered pre-VAD audio
        """
        await self.event_to_server(
            AudioStart(
                rate=self.mic_format.rate,
                width=self.mic_format.width,
                channels=self.mic_format.channels,
            ).event()
        )
        await self._send_run_pipeline()
        await self.drain_vad_buffer()

    @on_state_change(new_state=SatState.STREAM_TO_SERVER)
    @on_state_change(new_state=SatState.FOLLOWUP)
    async def on_listen_start(self, old_state: SatState, new_state: SatState) -> None:
        """
        When we begin streaming or start listening for a followup response,
        play an alert sound to indicate to the user that we're listening.
        """
        if self.settings.fsm.listen_start_alert_wav:
            await self.play_wav_background(self.settings.fsm.listen_start_alert_wav)
        if self.settings.fsm.listen_stop_alert_wav:
            await self.play_wav_background(self.settings.fsm.listen_stop_alert_wav)

    @on_state_change(old_state=SatState.STREAM_TO_SERVER)
    async def on_stream_stop(self, old_state: SatState, new_state: SatState) -> None:
        """
        When we stop streaming audio to the server, play an alert sound
        to indicate to the user that we're no longer listening and send
        and audio stop event to the server.
        """
        if self.settings.fsm.listen_stop_alert_wav:
            await self.play_wav_background(self.settings.fsm.listen_stop_alert_wav)
        await self.event_to_server(AudioStop().event())

    async def handle_state_change(
        self, old_state: SatState, new_state: SatState
    ) -> None:
        """
        When the satellite transitions from old_state to new_state,
        trigger all state change listeners that apply.
        """
        async with asyncio.TaskGroup() as tg:
            for predicate, handler in _state_change_listeners:
                if predicate(old_state, new_state):
                    tg.create_task(handler(self, old_state, new_state))

    async def drain_vad_buffer(self) -> None:
        """Send the user speech that was buffered before VAD to the server, and reset the VAD buffer."""
        if self.vad_buffer is not None and self.vad_chunk is not None:
            chunk = self.vad_chunk
            await self.event_to_server(
                AudioChunk(
                    rate=chunk.rate,
                    width=chunk.width,
                    channels=chunk.channels,
                    audio=self.vad_buffer.getvalue(),
                ).event()
            )
        self._reset_vad()

    def time_since_last_event(
        self, event_type: SatEvent, now: Optional[float] = None
    ) -> Optional[float]:
        """Return the time the event was last marked, in seconds"""
        if now is None:
            now = time.monotonic()
        event_ts = self.sat_events.get(event_type)
        if event_ts is None:
            return None
        return now - event_ts

    def get_next_state(self) -> SatState:
        """
        Check our current state and past events to determine what the next state should be.
        The return value is either the current state, or a new state.
        """
        last_state_change = self.time_since_last_event(SatEvent.STATE_CHANGE)
        assert last_state_change is not None, "State change event should always exist"
        last_vad = self.time_since_last_event(SatEvent.VAD)

        if self.time_since_last_event(SatEvent.SERVER_DISCONNECT) is not None:
            return SatState.PAUSED
        elif self.sat_state == SatState.PAUSED:
            if self.time_since_last_event(SatEvent.SERVER_CONNECT) is not None:
                return SatState.MONITOR
        elif self.sat_state == SatState.MONITOR:
            last_wakeword = self.time_since_last_event(SatEvent.WAKEWORD)
            if last_wakeword is not None:
                return SatState.STREAM_TO_SERVER
        elif self.sat_state == SatState.STREAM_TO_SERVER:
            if (
                last_vad is None
                and last_state_change > self.settings.fsm.stream_giveup_delay
            ):
                return SatState.PLAYBACK
            elif last_vad is not None and last_vad > self.settings.fsm.stream_end_delay:
                return SatState.PLAYBACK
        elif self.sat_state == SatState.PLAYBACK:
            tts_end = self.time_since_last_event(SatEvent.TTS_END)
            if self.time_since_last_event(SatEvent.PAUSE) is not None:
                return SatState.MONITOR
            elif tts_end is not None and tts_end > self.settings.fsm.tts_end_delay:
                return SatState.FOLLOWUP
        elif self.sat_state == SatState.FOLLOWUP:
            if self.time_since_last_event(SatEvent.PAUSE) is not None:
                return SatState.MONITOR
            elif (
                last_vad is not None
                and last_state_change - last_vad
                > self.settings.fsm.followup_vad_refractory
            ):
                return SatState.STREAM_TO_SERVER
            elif last_state_change > self.settings.fsm.followup_timeout:
                return SatState.MONITOR

        # no state change, return the current state
        return self.sat_state

    async def trigger_server_disonnected(self) -> None:
        await super().trigger_server_disonnected()
        self.mark_sat_event(SatEvent.SERVER_DISCONNECT)

    async def trigger_server_connected(self) -> None:
        await super().trigger_server_connected()
        self.mark_sat_event(SatEvent.SERVER_CONNECT)

    async def _snd_task_proc(self) -> None:
        """Snd service loop."""
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

                snd_event = await self._snd_queue.get()
                event = snd_event.event

                if snd_client is None:
                    snd_client = self._make_snd_client()
                    assert snd_client is not None
                    await snd_client.connect()
                    _LOGGER.debug("Connected to snd service")

                if AudioChunk.is_type(event.type):
                    chunk = AudioChunk.from_event(event)

                    if SatEvent.TTS_START not in self.sat_events:
                        self.mark_sat_event(SatEvent.TTS_START)
                    # Audio processing
                    if self.settings.snd.needs_processing:
                        audio_bytes = self._process_snd_audio(chunk.audio)
                        event = AudioChunk(
                            rate=chunk.rate,
                            width=chunk.width,
                            channels=chunk.channels,
                            audio=audio_bytes,
                        ).event()

                    self.expected_playback_end = (
                        max(time.monotonic(), self.expected_playback_end)
                        + chunk.seconds
                    )
                await snd_client.write_event(event)

                if self.settings.snd.disconnect_after_stop and AudioStop.is_type(
                    event.type
                ):
                    if isinstance(snd_client, SndProcessAsyncClient):
                        self.sat_events[SatEvent.TTS_END] = self.expected_playback_end
                    await _disconnect()
                    if snd_event.is_tts:
                        await self.trigger_played()
                    snd_client = None  # reconnect on next event
            except asyncio.CancelledError:
                break
            except Exception:
                _LOGGER.exception("Unexpected error in snd read task")
                await _disconnect()
                snd_client = None  # reconnect
                self._snd_queue = None
                await asyncio.sleep(self.settings.snd.reconnect_seconds)

        await _disconnect()

    def _reset_vad(self):
        """Reset state of VAD."""
        self.vad(None)
        if self.vad_buffer is not None:
            self.vad_buffer.put(bytes(self.vad_buffer.maxlen))
            self.vad_chunk = None

    async def event_from_wake(self, event: Event) -> None:
        if Info.is_type(event.type):
            self._wake_info = Info.from_event(event)
            self._wake_info_ready.set()
            return

        if Detection.is_type(event.type):
            detection = Detection.from_event(event)
            # Stop debug recording (wake)
            if self.wake_audio_writer is not None:
                self.wake_audio_writer.stop()
            # Start debug recording (stt)
            if self.stt_audio_writer is not None:
                self.stt_audio_writer.start(timestamp=self._debug_recording_timestamp)

            _LOGGER.info("wakeword detected")
            self.mark_sat_event(SatEvent.WAKEWORD)

            await self.event_to_server(event)
            await self.forward_event(event)  # forward to event service

    async def update_info(self, info: Info) -> None:
        self._wake_info = None
        self._wake_info_ready.clear()
        await self.event_to_wake(Describe().event())

        try:
            await asyncio.wait_for(
                self._wake_info_ready.wait(), timeout=_WAKE_INFO_TIMEOUT
            )

            if self._wake_info is not None:
                # Update wake info only
                info.wake = self._wake_info.wake
        except asyncio.TimeoutError:
            _LOGGER.warning("Failed to get info from wake service")
