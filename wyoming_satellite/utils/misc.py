"""Miscellaneous utilities."""
import argparse
import asyncio
import logging
import shlex
import uuid
from typing import List, Optional

_LOGGER = logging.getLogger()


async def run_event_command(
    command: Optional[List[str]], command_input: Optional[str] = None
) -> None:
    """Run a custom event command with optional input."""
    if not command:
        return

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
