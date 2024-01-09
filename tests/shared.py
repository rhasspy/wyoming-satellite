"""Shared code for Wyoming satellite tests."""
from wyoming.audio import AudioChunk

AUDIO_CHUNK = AudioChunk(
    rate=16000, width=2, channels=1, audio=bytes([255] * 960)  # 30ms
)
