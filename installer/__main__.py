"""Command-line installer."""
import array
import math
import logging
import json
import shlex
import subprocess
import shutil
import sys
import time
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor, Future
from enum import Enum
from dataclasses import dataclass, fields, asdict, field
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional, Union

from .const import (
    Settings,
    PROGRAM_DIR,
    LOCAL_DIR,
    SatelliteType,
    SERVICES_DIR,
    WakeWordSystem,
)
from .whiptail import run_with_gauge, menu, ItemType, msgbox, error, passwordbox
from .satellite import configure_satellite
from .microphone import configure_microphone
from .speakers import configure_speakers
from .drivers import install_drivers
from .wake_word import configure_wake_word

_LOGGER = logging.getLogger()


def main() -> None:
    LOCAL_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=LOCAL_DIR / "installer.log", filemode="w", level=logging.DEBUG
    )

    settings = Settings.load()

    venv_dir = PROGRAM_DIR / ".venv"
    if not venv_dir.exists():
        run_with_gauge(
            "Installing satellite base...", [[str(PROGRAM_DIR / "script" / "setup")]]
        )

    choice: Optional[str] = None
    while True:
        choice = main_menu(choice)

        if choice == "satellite":
            configure_satellite(settings)
        elif choice == "microphone":
            configure_microphone(settings)
        elif choice == "speakers":
            configure_speakers(settings)
        elif choice == "wake":
            configure_wake_word(settings)
        elif choice == "drivers":
            install_drivers(settings)
        elif choice == "apply":
            apply_settings(settings)
        else:
            break


def main_menu(last_choice: Optional[str]) -> Optional[str]:
    items: List[ItemType] = [
        ("satellite", "Satellite"),
        ("microphone", "Microphone"),
        ("speakers", "Speakers"),
        ("wake", "Wake Word"),
        ("drivers", "Drivers"),
        ("apply", "Apply Settings"),
    ]

    return menu(
        "Main",
        items,
        selected_item=last_choice,
        menu_args=["--ok-button", "Select", "--cancel-button", "Exit"],
    )


# -----------------------------------------------------------------------------


def pip_install(*args) -> List[str]:
    return [
        str(PROGRAM_DIR / ".venv" / "bin" / "pip3"),
        "install",
        "--extra-index-url",
        "https://www.piwheels.org/simple",
        "-f",
        "https://synesthesiam.github.io/prebuilt-apps/",
    ] + list(args)


def stop_services(password: str) -> None:
    stop_commands = []
    for service in ("satellite", "openwakeword", "porcupine1", "snowboy"):
        service_filename = f"wyoming-{service}.service"
        service_path = Path("/etc/systemd/system") / service_filename
        if not service_path.exists():
            continue

        stop_commands.append(["sudo", "-S", "systemctl", "stop", service_filename])
        stop_commands.append(["sudo", "-S", "systemctl", "disable", service_filename])

    run_with_gauge("Stopping Services...", stop_commands, sudo_password=password)


def generate_services(settings: Settings) -> None:
    SERVICES_DIR.mkdir(parents=True, exist_ok=True)

    user = subprocess.check_output(["id", "--name", "-u"], text=True).strip()
    satellite_command: List[str] = [
        str(PROGRAM_DIR / "script" / "run"),
        "--name",
        settings.satellite_name,
        "--uri",
        "tcp://0.0.0.0:10700",
        "--mic-command",
        f"arecord -D {settings.microphone_device} -q -r 16000 -c 1 -f S16_LE -t raw",
    ]
    satellite_requires: List[str] = []

    if settings.sound_device is not None:
        # Audio output
        satellite_command.extend(
            [
                "--snd-command",
                f"aplay -D {settings.sound_device} -q -r 22050 -c 1 -f S16_LE -t raw",
            ]
        )

        for sound_name in settings.feedback_sounds:
            # Try local/sounds first
            sound_path = LOCAL_DIR / "sounds" / f"{sound_name}.wav"
            if not sound_path.exists():
                sound_path = PROGRAM_DIR / "sounds" / f"{sound_name}.wav"

            satellite_command.extend([f"--{sound_name}-wav", str(sound_path)])

    if settings.satellite_type == SatelliteType.VAD:
        # Voice activity detect
        satellite_command.append("--vad")
    elif settings.satellite_type == SatelliteType.WAKE:
        # Local wake word detection
        assert settings.wake_word_system is not None, "Wake word system not set"
        wake_word = settings.wake_word.get(settings.wake_word_system)
        assert wake_word, "No wake word set"

        wake_word_service = "wyoming-" + str(settings.wake_word_system).lower()
        wake_word_dir = LOCAL_DIR / wake_word_service
        wake_word_command = [
            str(wake_word_dir / "script" / "run"),
            "--uri",
            "tcp://127.0.0.1:10400",
        ]

        if settings.wake_word_system in (
            WakeWordSystem.OPENWAKEWORD,
            WakeWordSystem.SNOWBOY,
        ):
            wake_word_command.extend(
                [
                    "--custom-model-dir",
                    str(
                        LOCAL_DIR
                        / "custom-wake-words"
                        / WakeWordSystem(settings.wake_word_system).value
                    ),
                ]
            )

        if settings.debug_enabled:
            wake_word_command.append("--debug")

        wake_word_command_str = shlex.join(wake_word_command)

        with open(
            SERVICES_DIR / f"{wake_word_service}.service", "w", encoding="utf-8"
        ) as service_file:
            print("[Unit]", file=service_file)
            print(f"Description={settings.wake_word_system}", file=service_file)
            print("", file=service_file)
            print("[Service]", file=service_file)
            print("Type=simple", file=service_file)
            print(f"User={user}", file=service_file)
            print(f"ExecStart={wake_word_command_str}", file=service_file)
            print(f"WorkingDirectory={wake_word_dir}", file=service_file)
            print("Restart=always", file=service_file)
            print("RestartSec=1", file=service_file)
            print("", file=service_file)
            print("[Install]", file=service_file)
            print("WantedBy=default.target", file=service_file)

        satellite_command.extend(
            [
                "--wake-uri",
                "tcp://127.0.0.1:10400",
                "--wake-word-name",
                wake_word,
            ]
        )
        satellite_requires.append(f"{wake_word_service}.service")

    if settings.debug_enabled:
        satellite_command.extend(
            ["--debug", "--debug-recording-dir", str(LOCAL_DIR / "debug-recording")]
        )

    satellite_command_str = shlex.join(satellite_command)

    with open(
        SERVICES_DIR / "wyoming-satellite.service", "w", encoding="utf-8"
    ) as service_file:
        print("[Unit]", file=service_file)
        print("Description=Wyoming Satellite", file=service_file)
        print("Wants=network-online.target", file=service_file)
        print("After=network-online.target", file=service_file)
        for requires in satellite_requires:
            print(f"Requires={requires}", file=service_file)

        print("", file=service_file)
        print("[Service]", file=service_file)
        print("Type=simple", file=service_file)
        print(f"User={user}", file=service_file)
        print(f"ExecStart={satellite_command_str}", file=service_file)
        print(f"WorkingDirectory={PROGRAM_DIR}", file=service_file)
        print("Restart=always", file=service_file)
        print("RestartSec=1", file=service_file)
        print("", file=service_file)
        print("[Install]", file=service_file)
        print("WantedBy=default.target", file=service_file)


def apply_settings(settings: Settings) -> None:
    if settings.microphone_device is None:
        msgbox("Please configure microphone")
        return

    # Satellite venv
    venv_dir = PROGRAM_DIR / ".venv"
    if not venv_dir.exists():
        result = run_with_gauge(
            "Creating virtual environment...", [str(PROGRAM_DIR / "script" / "setup")]
        )
        if not result:
            error("creating virtual environment")
            return

    # silero (vad)
    if settings.satellite_type == SatelliteType.VAD:
        result = run_with_gauge(
            "Installing vad...",
            [pip_install("-r", str(PROGRAM_DIR / "requirements_vad.txt"))],
        )
        if not result:
            error("installing vad")
            return

    # webrtc (audio enhancements)
    if (settings.noise_suppression_level > 0) or (settings.auto_gain > 0):
        result = run_with_gauge(
            "Installing audio enhancements...",
            [
                pip_install(
                    "-r", str(PROGRAM_DIR / "requirements_audio_enhancement.txt")
                )
            ],
        )
        if not result:
            error("installing audio enhancements")
            return

    generate_services(settings)

    password = passwordbox("sudo password:")
    if not password:
        return

    stop_services(password)

    # Install and run
    installed_services = ["satellite"]
    if settings.satellite_type == SatelliteType.WAKE:
        assert settings.wake_word_system is not None, "No wake word system"
        installed_services.append(
            WakeWordSystem(settings.wake_word_system).value.lower()
        )

    install_commands = []
    for service in installed_services:
        service_filename = f"wyoming-{service}.service"
        install_commands.append(
            [
                "sudo",
                "-S",
                "cp",
                str(SERVICES_DIR / service_filename),
                "/etc/systemd/system/",
            ]
        )

    install_commands.append(["sudo", "-S", "systemctl", "daemon-reload"])

    # Copy first, then enable and start
    for service in installed_services:
        install_commands.append(["sudo", "-S", "systemctl", "enable", service_filename])

    install_commands.append(["sudo", "-S", "systemctl", "start", "wyoming-satellite.service"])

    success = run_with_gauge(
        "Installing Services...", install_commands, sudo_password=password
    )
    if success:
        msgbox("Successfully installed services")
    else:
        error("installing services")


# -----------------------------------------------------------------------------


if __name__ == "__main__":
    main()
