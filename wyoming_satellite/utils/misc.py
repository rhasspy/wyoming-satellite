"""Miscellaneous utilities."""
import argparse
import asyncio
import json
import logging
import re
import shlex
import unicodedata
import uuid
from functools import lru_cache
from typing import List, Optional, Union

from wyoming.event import Eventable

_LOGGER = logging.getLogger()


async def run_event_command(
    command: Optional[List[str]], command_input: Optional[Union[str, Eventable]] = None
) -> None:
    """Run a custom event command with optional input."""
    if not command:
        return

    if isinstance(command_input, Eventable):
        # Convert event to JSON
        event_dict = command_input.event().to_dict()
        command_input = json.dumps(event_dict, ensure_ascii=False)

    _LOGGER.debug("Running %s", command)
    program, *program_args = command
    proc = await asyncio.create_subprocess_exec(
        program, *program_args, stdin=asyncio.subprocess.PIPE
    )
    assert proc.stdin is not None

    if command_input:
        await proc.communicate(input=command_input.encode("utf-8"))
    else:
        proc.stdin.close()
        await proc.wait()


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


def split_command(command: Optional[str]) -> Optional[List[str]]:
    """Split command line program/args if not empty."""
    if not command:
        return None

    return shlex.split(command)


@lru_cache
def normalize_wake_word(wake_word: str) -> str:
    """Normalizes a wake word name for comparison."""

    # Lower case
    wake_word = wake_word.strip().casefold()

    # Remove version numbers like v1.0
    wake_word = re.sub(r"v[0-9]+(\.[0-9])+", "", wake_word)

    # Replace anything besides letters/numbers with whitespace
    wake_word = "".join(
        c if unicodedata.category(c) in ("Ll", "Nd") else " " for c in wake_word
    )

    # Normalize whitespace
    wake_word = " ".join(wake_word.strip().split())

    return wake_word
