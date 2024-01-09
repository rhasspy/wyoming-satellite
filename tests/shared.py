"""Shared code for Wyoming satellite tests."""
from wyoming.info import Info, Attribution, Satellite
from wyoming.audio import AudioChunk

WYOMING_INFO = Info(
    satellite=Satellite(
        name="test satellite",
        area="test area",
        description="test description",
        attribution=Attribution(name="", url=""),
        installed=True,
    )
)

AUDIO_CHUNK = AudioChunk(
    rate=16000, width=2, channels=1, audio=bytes([255] * 960)  # 30ms
)
