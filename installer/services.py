"""Systemd service management."""
import shlex
import subprocess
from pathlib import Path
from typing import List

from .const import (
    LOCAL_DIR,
    PROGRAM_DIR,
    SERVICES_DIR,
    SatelliteType,
    Settings,
    WakeWordSystem,
)
from .whiptail import error, msgbox, run_with_gauge


def stop_services(password: str) -> None:
    stop_commands = []
    for service in ("satellite", "wakeword", "event"):
        service_filename = f"wyoming-{service}.service"
        service_path = Path("/etc/systemd/system") / service_filename
        if not service_path.exists():
            continue

        stop_commands.append(["sudo", "-S", "systemctl", "stop", service_filename])
        stop_commands.append(["sudo", "-S", "systemctl", "disable", service_filename])

    run_with_gauge("Stopping Services...", stop_commands, sudo_password=password)


def generate_services(settings: Settings) -> None:
    SERVICES_DIR.mkdir(parents=True, exist_ok=True)

    user_id = subprocess.check_output(["id", "-u"], text=True).strip()
    user_name = subprocess.check_output(["id", "--name", "-u"], text=True).strip()

    satellite_command: List[str] = [
        str(PROGRAM_DIR / "script" / "run"),
        "--name",
        settings.satellite.name,
        "--uri",
        "tcp://0.0.0.0:10700",
        "--mic-command",
        f"arecord -D {settings.mic.device} -q -r 16000 -c 1 -f S16_LE -t raw",
    ]
    satellite_requires: List[str] = []

    if settings.snd.device is not None:
        # Audio output
        satellite_command.extend(
            [
                "--snd-command",
                f"aplay -D {settings.snd.device} -q -r 22050 -c 1 -f S16_LE -t raw",
            ]
        )

        if settings.snd.volume_multiplier != 1.0:
            satellite_command.extend(
                ["--snd-volume-multiplier", str(settings.snd.volume_multiplier)]
            )

        for sound_name in settings.snd.feedback_sounds:
            # Try local/sounds first
            sound_path = LOCAL_DIR / "sounds" / f"{sound_name}.wav"
            if not sound_path.exists():
                sound_path = PROGRAM_DIR / "sounds" / f"{sound_name}.wav"

            satellite_command.extend([f"--{sound_name}-wav", str(sound_path)])

    if settings.mic.noise_suppression > 0:
        satellite_command.extend(
            ["--mic-noise-suppression", str(settings.mic.noise_suppression)]
        )

    if settings.mic.auto_gain > 0:
        satellite_command.extend(["--mic-auto-gain", str(settings.mic.auto_gain)])

    if settings.mic.volume_multiplier != 1.0:
        satellite_command.extend(
            ["--mic-volume-multiplier", str(settings.mic.volume_multiplier)]
        )

    if settings.satellite.type == SatelliteType.VAD:
        # Voice activity detect
        satellite_command.append("--vad")
    elif settings.satellite.type == SatelliteType.WAKE:
        # Local wake word detection
        assert settings.wake.system is not None, "Wake word system not set"

        wake_word_service = "wyoming-wakeword"
        wake_word_dir = LOCAL_DIR / (
            "wyoming-" + WakeWordSystem(settings.wake.system).value.lower()
        )
        wake_word_command = [
            str(wake_word_dir / "script" / "run"),
            "--uri",
            "tcp://127.0.0.1:10400",
        ]

        if settings.wake.system == WakeWordSystem.OPENWAKEWORD:
            wake_word = settings.wake.openwakeword.wake_word
            wake_word_command.extend(
                [
                    "--threshold",
                    str(settings.wake.openwakeword.threshold),
                    "--trigger-level",
                    str(settings.wake.openwakeword.trigger_level),
                    "--custom-model-dir",
                    str(LOCAL_DIR / "custom-wake-words" / "openWakeWord"),
                ]
            )
        elif settings.wake.system == WakeWordSystem.PORCUPINE1:
            wake_word = settings.wake.porcupine1.wake_word
            wake_word_command.extend(
                ["--sensitivity", str(settings.wake.porcupine1.sensitivity)]
            )
        elif settings.wake.system == WakeWordSystem.SNOWBOY:
            wake_word = settings.wake.snowboy.wake_word
            wake_word_command.extend(
                [
                    "--sensitivity",
                    str(settings.wake.snowboy.sensitivity),
                    "--custom-model-dir",
                    str(LOCAL_DIR / "custom-wake-words" / "snowboy"),
                ]
            )
        else:
            raise ValueError(settings.wake.system)

        if settings.satellite.debug:
            wake_word_command.append("--debug")

        wake_word_command_str = shlex.join(wake_word_command)

        with open(
            SERVICES_DIR / f"{wake_word_service}.service", "w", encoding="utf-8"
        ) as service_file:
            print("[Unit]", file=service_file)
            print(
                f"Description={WakeWordSystem(settings.wake.system).value}",
                file=service_file,
            )
            print("", file=service_file)
            print("[Service]", file=service_file)
            print("Type=simple", file=service_file)
            print(f"User={user_name}", file=service_file)
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

    if settings.satellite.event_service_command:
        event_service = "wyoming-event"
        event_command_str = shlex.join(settings.satellite.event_service_command)
        with open(
            SERVICES_DIR / f"{event_service}.service", "w", encoding="utf-8"
        ) as service_file:
            print("[Unit]", file=service_file)
            print("Description=Event service", file=service_file)
            print("", file=service_file)
            print("[Service]", file=service_file)
            print("Type=simple", file=service_file)
            print(f"User={user_name}", file=service_file)
            print(f"ExecStart={event_command_str}", file=service_file)
            print(f"WorkingDirectory={PROGRAM_DIR}", file=service_file)
            print("Restart=always", file=service_file)
            print("RestartSec=1", file=service_file)
            print("", file=service_file)
            print("[Install]", file=service_file)
            print("WantedBy=default.target", file=service_file)

        satellite_command.extend(["--event-uri", "tcp://127.0.0.1:10500"])
        satellite_requires.append(f"{event_service}.service")

    if settings.satellite.debug:
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
        print(f"User={user_name}", file=service_file)

        # For PulseAudio
        print(f"Environment=XDG_RUNTIME_DIR=/run/user/{user_id}", file=service_file)

        print(f"ExecStart={satellite_command_str}", file=service_file)
        print(f"WorkingDirectory={PROGRAM_DIR}", file=service_file)
        print("Restart=always", file=service_file)
        print("RestartSec=1", file=service_file)
        print("", file=service_file)
        print("[Install]", file=service_file)
        print("WantedBy=default.target", file=service_file)


def install_services(settings: Settings, password: str):
    # Install and run
    installed_services = ["satellite"]
    if settings.satellite.type == SatelliteType.WAKE:
        assert settings.wake.system is not None, "No wake word system"
        installed_services.append("wakeword")

    if settings.satellite.event_service_command:
        installed_services.append("event")

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

    install_commands.append(
        ["sudo", "-S", "systemctl", "enable", "--now", "wyoming-satellite.service"]
    )

    success = run_with_gauge(
        "Installing Services...", install_commands, sudo_password=password
    )
    if success:
        msgbox("Successfully installed services")
    else:
        error("installing services")
