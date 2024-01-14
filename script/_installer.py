#!/usr/bin/env python3
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

_DIR = Path(__file__).parent
_PROGRAM_DIR = _DIR.parent
_LOCAL_DIR = _PROGRAM_DIR / "local"
_SETTINGS_PATH = _LOCAL_DIR / "settings.json"
_LOGGER = logging.getLogger()

_RECORD_SECONDS = 8
_RECORD_RMS_MIN = 30

TITLE = "Wyoming Satellite"
WIDTH = "75"
HEIGHT = "20"
LIST_HEIGHT = "12"

ItemType = Union[str, Tuple[Any, str]]


class SatelliteType(str, Enum):
    ALWAYS_STREAMING = "always"
    VAD = "vad"
    WAKE = "wake"


class WakeWordSystem(str, Enum):
    OPENWAKEWORD = "openWakeWord"
    PORCUPINE1 = "porcupine1"
    SNOWBOY = "snowboy"


@dataclass
class Settings:
    microphone_device: Optional[str] = None
    noise_suppression_level: int = 0
    auto_gain: int = 0
    mic_volume_multiplier: float = 1.0

    sound_device: Optional[str] = None
    feedback_sounds: List[str] = field(default_factory=list)

    wake_word_system: Optional[WakeWordSystem] = None
    wake_word: Dict[WakeWordSystem, str] = field(default_factory=dict)

    satellite_name: str = "Wyoming Satellite"
    satellite_type: SatelliteType = SatelliteType.ALWAYS_STREAMING

    debug_enabled: bool = False

    @staticmethod
    def load() -> "Settings":
        kwargs: Dict[str, Any] = {}

        if _SETTINGS_PATH.exists():
            _LOGGER.debug("Loading settings from %s", _SETTINGS_PATH)
            with open(_SETTINGS_PATH, "r", encoding="utf-8") as settings_file:
                settings_dict = json.load(settings_file)

            for settings_field in fields(Settings):
                value = settings_dict.get(settings_field.name)
                if value is not None:
                    kwargs[settings_field.name] = value

        return Settings(**kwargs)

    def save(self) -> None:
        _LOGGER.debug("Saving settings to %s", _SETTINGS_PATH)

        settings_dict = asdict(self)
        _SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)

        with open(_SETTINGS_PATH, "w", encoding="utf-8") as settings_file:
            json.dump(settings_dict, settings_file, ensure_ascii=False, indent=2)


# -----------------------------------------------------------------------------


def main() -> None:
    _LOCAL_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=_LOCAL_DIR / "installer.log", filemode="w", level=logging.DEBUG
    )

    settings = Settings.load()

    venv_dir = _PROGRAM_DIR / ".venv"
    if not venv_dir.exists():
        run_with_gauge(
            "Installing satellite base...", [[str(_PROGRAM_DIR / "script" / "setup")]]
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
        elif choice == "services":
            configure_services(settings)
        elif choice == "drivers":
            install_drivers(settings)
        else:
            break


def main_menu(last_choice: Optional[str]) -> Optional[str]:
    items: List[ItemType] = [
        ("satellite", "Satellite"),
        ("microphone", "Microphone"),
        ("speakers", "Speakers"),
        ("wake", "Wake Word"),
        ("services", "Services"),
        ("drivers", "Drivers"),
    ]

    return menu(
        "Main",
        items,
        selected_item=last_choice,
        menu_args=["--ok-button", "Select", "--cancel-button", "Exit"],
    )


# -----------------------------------------------------------------------------
# Satellite
# -----------------------------------------------------------------------------


def configure_satellite(settings: Settings) -> None:
    choice: Optional[str] = None
    while True:
        choice = satellite_menu(choice)

        if choice == "name":
            set_satellite_name(settings)
        elif choice == "type":
            set_satellite_type(settings)
        else:
            break


def satellite_menu(last_choice: Optional[str]) -> Optional[str]:
    return menu(
        "Main > Satellite",
        [
            ("name", "Name"),
            ("type", "Type"),
        ],
        selected_item=last_choice,
        menu_args=["--ok-button", "Select", "--cancel-button", "Back"],
    )


def set_satellite_name(settings: Settings) -> None:
    name = inputbox("Satellite Name:", settings.satellite_name)
    if name:
        settings.satellite_name = name
        settings.save()


def set_satellite_type(settings: Settings) -> None:
    satellite_type = radiolist(
        "Satellite Type:",
        [
            (SatelliteType.ALWAYS_STREAMING, "Always streaming"),
            (SatelliteType.VAD, "Voice activity detection"),
            (SatelliteType.WAKE, "Local wake word detection"),
        ],
        settings.satellite_type,
    )

    if satellite_type == SatelliteType.VAD:
        result = run_with_gauge(
            "Installing vad...",
            [pip_install("-r", str(_PROGRAM_DIR / "requirements_vad.txt"))],
        )
        if not result:
            msgbox(
                "An error occurred while installed vad. "
                "See local/installer.log for details."
            )
            return

    if satellite_type is not None:
        settings.satellite_type = satellite_type
        settings.save()


# -----------------------------------------------------------------------------
# Microphone
# -----------------------------------------------------------------------------


def configure_microphone(settings: Settings) -> None:
    choice: Optional[str] = None
    while True:
        choice = microphone_menu(choice)

        if choice == "detect":
            # Automatically detect microphone with hightest RMS
            best_device: Optional[str] = None
            best_rms: Optional[float] = None

            devices = get_microphone_devices()
            with ThreadPoolExecutor() as executor:
                futures: Dict[str, Future] = {}
                for device in devices:
                    futures[device] = executor.submit(_record_proc, device)

                gauge("Speak loudly into the microphone.", _RECORD_SECONDS)
                for device, future in futures.items():
                    device_rms = future.result()
                    if device_rms < _RECORD_RMS_MIN:
                        continue

                    if (best_rms is None) or (device_rms > best_rms):
                        best_device = device
                        best_rms = device_rms

            if best_device is not None:
                msgbox(f"Successfully detected microphone: {best_device}")
                settings.microphone_device = best_device
                settings.save()
            else:
                msgbox("Audio was not detected from any microphone")
        elif choice == "list":
            # arecord -L
            microphone_device = radiolist(
                "Select ALSA Device:",
                get_microphone_devices(),
                settings.microphone_device,
            )
            if microphone_device:
                settings.microphone_device = microphone_device
                settings.save()
        elif choice == "manual":
            microphone_device = inputbox(
                "Enter ALSA Device:", settings.microphone_device
            )
            if microphone_device:
                settings.microphone_device = microphone_device
                settings.save()
        elif choice == "enhancements":
            configure_audio_enhancements(settings)
        # elif choice == "respeaker":
        #     if yesno(
        #         "ReSpeaker drivers for the Raspberry Pi will now be compiled and installed. "
        #         "This will take a while and require a reboot. "
        #         "Continue?"
        #     ):
        #         password = paswordbox("sudo password:")
        #         run_with_gauge(
        #             "Installing drivers...",
        #             [
        #                 [
        #                     "sudo",
        #                     "-S",
        #                     str(_PROGRAM_DIR / "etc" / "install-respeaker-drivers.sh"),
        #                 ]
        #             ],
        #             sudo_password=password,
        #         )

        #         msgbox(
        #             "Driver installation complete. "
        #             "Please reboot your Raspberry Pi and re-run the installer. "
        #             'Once rebooted, select the "seeed" microphone.'
        #         )

        #         sys.exit(0)
        else:
            break


def microphone_menu(last_choice: Optional[str]) -> Optional[str]:
    return menu(
        "Main > Microphone",
        [
            ("detect", "Autodetect"),
            ("list", "Select From List"),
            ("manual", "Enter Manually"),
            ("enhancements", "Audio Enhancements"),
        ],
        selected_item=last_choice,
        menu_args=["--ok-button", "Select", "--cancel-button", "Back"],
    )


def get_microphone_devices() -> List[str]:
    devices = []
    lines = subprocess.check_output(["arecord", "-L"]).decode("utf-8").splitlines()
    for line in lines:
        line = line.strip()
        if line.startswith("plughw:"):
            devices.append(line)

    return devices


def _record_proc(device: str) -> float:
    try:
        audio = subprocess.check_output(
            [
                "arecord",
                "-q",
                "-D",
                device,
                "-r",
                "16000",
                "-c",
                "1",
                "-f",
                "S16_LE",
                "-t",
                "raw",
                "-d",
                str(_RECORD_SECONDS),
            ],
            stderr=subprocess.DEVNULL,
        )

        # 16-bit mono
        audio_array = array.array("h", audio)
        rms = math.sqrt(
            (1 / len(audio_array) * sum(x * x for x in audio_array.tolist()))
        )
        return rms
    except Exception:
        _LOGGER.exception("Error recording from device: %s", device)

    return 0


def configure_audio_enhancements(settings: Settings) -> None:
    choice: Optional[str] = None
    while True:
        choice = audio_enhancements_menu(choice)

        if choice == "noise":
            result = radiolist(
                "Noise Suppression Level",
                [(0, "Off"), (1, "Low"), (2, "Medium"), (3, "High"), (4, "Maximum")],
                settings.noise_suppression_level,
            )
            if result is not None:
                settings.noise_suppression_level = result
                settings.save()
        elif choice == "gain":
            while True:
                result = inputbox("Auto Gain (0-31 dbFS)", settings.auto_gain)
                if result is not None:
                    try:
                        auto_gain = int(result)
                    except ValueError:
                        msgbox("Invalid value")
                        continue

                    if 0 <= auto_gain <= 31:
                        settings.auto_gain = auto_gain
                        settings.save()
                        break

                    msgbox("Must be 0-31")
        elif choice == "multiplier":
            while True:
                result = inputbox("Volume Multipler (1 = default)", settings.mic_volume_multiplier)
                if result is not None:
                    try:
                        volume_multiplier = float(result)
                    except ValueError:
                        msgbox("Invalid value")
                        continue

                    if volume_multiplier > 0:
                        settings.mic_volume_multiplier = volume_multiplier
                        settings.save()
                        break

                    msgbox("Must be > 0")
        else:
            break


def audio_enhancements_menu(last_choice: Optional[str]) -> Optional[str]:
    return menu(
        "Main > Microphone > Audio Enhancements",
        [
            ("noise", "Noise Suppression"),
            ("gain", "Auto Gain"),
            ("multiplier", "Volume Multiplier"),
        ],
        selected_item=last_choice,
        menu_args=["--ok-button", "Select", "--cancel-button", "Back"],
    )


# -----------------------------------------------------------------------------
# Sound
# -----------------------------------------------------------------------------


def configure_sound(settings: Settings) -> None:
    while True:
        choice = sound_menu()

        if choice == "detect":
            pass
        elif choice == "list":
            sound_device = radiolist(
                "Select ALSA Device:",
                get_sound_devices(),
                settings.sound_device,
            )
            if sound_device:
                settings.sound_device = sound_device
                settings.save()
        elif choice == "manual":
            sound_device = inputbox("Enter ALSA Device:", settings.sound_device)
            if sound_device:
                settings.sound_device = sound_device
                settings.save()
        elif choice == "disable":
            settings.sound_device = None
            settings.save()
            msgbox("Sound disabled")
        elif choice == "feedback":
            feedback_sounds = checklist(
                "Enabled Sounds:",
                [("awake", "On wake-up"), ("done", "After voice command")],
                settings.feedback_sounds,
            )

            if feedback_sounds is not None:
                settings.feedback_sounds = feedback_sounds
                settings.save()
        else:
            break


def sound_menu() -> Optional[str]:
    return menu(
        "Configure Sound",
        [
            ("detect", "Autodetect"),
            ("list", "Select From List"),
            ("manual", "Enter Manually"),
            ("disable", "Disable Sound"),
            ("feedback", "Toggle Feedback Sounds"),
        ],
        menu_args=["--ok-button", "Select", "--cancel-button", "Back"],
    )


def get_sound_devices() -> List[str]:
    devices = []
    lines = subprocess.check_output(["aplay", "-L"]).decode("utf-8").splitlines()
    for line in lines:
        line = line.strip()
        if line.startswith("plughw:"):
            devices.append(line)

    return devices


# -----------------------------------------------------------------------------
# Wake Word
# -----------------------------------------------------------------------------


def configure_wake_word(settings: Settings) -> None:
    if settings.satellite_type != SatelliteType.WAKE:
        msgbox("Satellite type is not set to local wake word.")
        return

    while True:
        choice = wake_word_menu(settings)

        if choice == "system":
            wake_word_system = radiolist(
                "Wake Word System:",
                [v.value for v in WakeWordSystem],
                settings.wake_word_system,
            )
            if wake_word_system is not None:
                install_wake_word(settings, WakeWordSystem(wake_word_system))
        elif choice == "wake_word":
            select_wake_word(settings)
        else:
            break


def wake_word_menu(settings: Settings) -> Optional[str]:
    items = [("system", "Select System")]
    if settings.wake_word_system is not None:
        items.append(("wake_word", "Select Wake Word"))

    return menu(
        "Configure Wake Word",
        items,
        menu_args=["--ok-button", "Select", "--cancel-button", "Back"],
    )


def install_wake_word(settings: Settings, wake_word_system: WakeWordSystem) -> None:
    if wake_word_system == WakeWordSystem.OPENWAKEWORD:
        oww_dir = _LOCAL_DIR / "wyoming-openwakeword"
        if not oww_dir.exists():
            success = run_with_gauge(
                "Installing openWakeWord",
                [
                    [
                        "git",
                        "clone",
                        "https://github.com/rhasspy/wyoming-openwakeword.git",
                        str(oww_dir),
                    ],
                    [str(oww_dir / "script" / "setup")],
                ],
            )

            if success:
                msgbox("openWakeWord installed successfully")
            else:
                msgbox(
                    "An error occurred while installing openWakeWord. "
                    "See local/installer.log for details."
                )

                try:
                    shutil.rmtree(oww_dir)
                except Exception:
                    pass

                return

        settings.wake_word_system = wake_word_system
        settings.wake_word.setdefault(WakeWordSystem.OPENWAKEWORD, "ok_nabu")
        settings.save()
    elif wake_word_system == WakeWordSystem.PORCUPINE1:
        porcupine1_dir = _LOCAL_DIR / "wyoming-porcupine1"
        if not porcupine1_dir.exists():
            success = run_with_gauge(
                "Installing porcupine1",
                [
                    [
                        "git",
                        "clone",
                        "https://github.com/rhasspy/wyoming-porcupine1.git",
                        str(porcupine1_dir),
                    ],
                    [str(porcupine1_dir / "script" / "setup")],
                ],
            )

            if success:
                msgbox("porcupine1 installed successfully")
            else:
                msgbox(
                    "An error occurred while installing porcupine1. "
                    "See local/installer.log for details."
                )

                try:
                    shutil.rmtree(porcupine1_dir)
                except Exception:
                    pass

                return

        settings.wake_word_system = wake_word_system
        settings.wake_word.setdefault(WakeWordSystem.PORCUPINE1, "porcupine")
        settings.save()
    elif settings.wake_word_system == WakeWordSystem.SNOWBOY:
        snowboy_dir = _LOCAL_DIR / "wyoming-snowboy"
        if not snowboy_dir.exists():
            success = run_with_gauge(
                "Installing snowboy",
                [
                    [
                        "git",
                        "clone",
                        "https://github.com/rhasspy/wyoming-snowboy.git",
                        str(snowboy_dir),
                    ],
                    [str(snowboy_dir / "script" / "setup")],
                ],
            )

            if success:
                msgbox("snowboy installed successfully")
            else:
                msgbox(
                    "An error occurred while installing snowboy. "
                    "See local/installer.log for details."
                )

                try:
                    shutil.rmtree(snowboy_dir)
                except Exception:
                    pass

                return

        settings.wake_word_system = wake_word_system
        settings.wake_word.setdefault(WakeWordSystem.SNOWBOY, "snowboy")
        settings.save()


def select_wake_word(settings: Settings) -> None:
    if settings.wake_word_system == WakeWordSystem.OPENWAKEWORD:
        wake_word = radiolist(
            "Wake Word:",
            [
                ("ok_nabu", "ok nabu"),
                ("hey_jarvis", "hey jarvis"),
                ("alexa", "alexa"),
                ("hey_mycroft", "hey mycroft"),
                ("community", "Community Wake Words"),
            ],
            settings.wake_word.get(WakeWordSystem.OPENWAKEWORD),
        )

        if wake_word is not None:
            settings.wake_word[WakeWordSystem.OPENWAKEWORD] = wake_word
            settings.save()

    elif settings.wake_word_system == WakeWordSystem.PORCUPINE1:
        wake_word = radiolist(
            "Wake Word:",
            [
                ("ok_nabu", "ok nabu"),
                ("hey_jarvis", "hey jarvis"),
                ("alexa", "alexa"),
                ("hey_mycroft", "hey mycroft"),
                ("community", "Community Wake Words"),
            ],
            settings.wake_word.get(WakeWordSystem.OPENWAKEWORD),
        )

        if wake_word is not None:
            settings.wake_word[WakeWordSystem.OPENWAKEWORD] = wake_word
            settings.save()

    elif settings.wake_word_system == WakeWordSystem.PORCUPINE1:
        wake_word = radiolist(
            "Wake Word:",
            [
                ("porcupine", "porcupine"),
            ],
            settings.wake_word.get(WakeWordSystem.PORCUPINE1),
        )

        if wake_word is not None:
            settings.wake_word[WakeWordSystem.PORCUPINE1] = wake_word
            settings.save()

    elif settings.wake_word_system == WakeWordSystem.SNOWBOY:
        wake_word = radiolist(
            "Wake Word:",
            [
                ("snowboy", "snowboy"),
                ("jarvis", "jarvis"),
                ("alexa", "alexa"),
                ("smart_mirror", "smart mirror"),
                ("view_glass", "view glass"),
                ("hey_extreme", "hey extreme"),
                ("neoya", "neoya"),
                ("subex", "subex"),
            ],
            settings.wake_word.get(WakeWordSystem.SNOWBOY),
        )

        if wake_word is not None:
            settings.wake_word[WakeWordSystem.SNOWBOY] = wake_word
            settings.save()


# -----------------------------------------------------------------------------
# Services
# -----------------------------------------------------------------------------


def generate_services(settings: Settings) -> None:
    if settings.microphone_device is None:
        msgbox("Please configure microphone")
        return

    services_dir = _LOCAL_DIR / "services"
    services_dir.mkdir(parents=True, exist_ok=True)

    user = subprocess.check_output(["id", "--name", "-u"], text=True).strip()

    satellite_command: List[str] = [
        str(_PROGRAM_DIR / "script" / "run"),
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
        satellite_command.append(
            f"aplay -D {settings.sound_device} -q -r 16000 -c 1 -f S16_LE -t raw"
        )

        for sound_name in settings.feedback_sounds:
            # Try local/sounds first
            sound_path = _LOCAL_DIR / "sounds" / f"{sound_name}.wav"
            if not sound_path.exists():
                sound_path = _PROGRAM_DIR / "sounds" / f"{sound_name}.wav"

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
        wake_word_dir = _LOCAL_DIR / wake_word_service
        wake_word_command = [
            str(wake_word_dir / "script" / "run"),
            "--uri",
            "tcp://127.0.0.1:10400",
        ]

        if settings.debug_enabled:
            wake_word_command.append("--debug")

        wake_word_command_str = shlex.join(wake_word_command)

        with open(
            services_dir / f"{wake_word_service}.service", "w", encoding="utf-8"
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
            ["--debug", "--debug-recording-dir", str(_LOCAL_DIR / "debug-recording")]
        )

    satellite_command_str = shlex.join(satellite_command)

    with open(
        services_dir / "wyoming-satellite.service", "w", encoding="utf-8"
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
        print(f"WorkingDirectory={_PROGRAM_DIR}", file=service_file)
        print("Restart=always", file=service_file)
        print("RestartSec=1", file=service_file)
        print("", file=service_file)
        print("[Install]", file=service_file)
        print("WantedBy=default.target", file=service_file)

    msgbox("Services generated")


def install_services(settings: Settings) -> None:
    services_dir = _LOCAL_DIR / "services"
    satellite_service_path = services_dir / "wyoming-satellite.service"

    if not satellite_service_path.exists():
        msgbox("Please generate services")
        return

    password = paswordbox("sudo password:")

    run_with_gauge(
        "Stopping Services...",
        [
            [
                "sudo",
                "-S",
                "systemctl",
                "disable",
                "--now",
                f"wyoming-{service}.service",
            ]
            for service in ("satellite", "openwakeword", "porcupine1", "snowboy")
        ],
        sudo_password=password,
    )

    installed_services = ["satellite"]
    install_commands = [["sudo", "-S", "systemctl", "daemon-reload"]]
    for service in installed_services:
        service_filename = f"wyoming-{service}.service"
        install_commands.append(
            [
                "sudo",
                "-S",
                "cp",
                str(services_dir / service_filename),
                "/etc/systemd/system/",
            ]
        )
        install_commands.append(
            ["sudo", "-S", "systemctl", "enable", "--now", service_filename]
        )

    success = run_with_gauge(
        "Installing Services...", install_commands, sudo_password=password
    )
    if success:
        msgbox("Successfully installed services")
    else:
        msgbox(
            "An error occurred while installing services. "
            "See local/installer.log for details."
        )


# -----------------------------------------------------------------------------
# whiptail
# -----------------------------------------------------------------------------


def whiptail(*args) -> Optional[str]:
    proc = subprocess.Popen(
        ["whiptail", "--title", TITLE] + list(args),
        stderr=subprocess.PIPE,
    )

    _stdout, stderr = proc.communicate()
    if proc.returncode != 0:
        return None

    return stderr.decode("utf-8")


def menu(
    text: str,
    items: Sequence[ItemType],
    selected_item: Optional[str] = None,
    menu_args: Optional[Sequence[str]] = None,
) -> Optional[str]:
    assert items, "No items"

    item_map: Dict[Optional[str], str] = {}
    item_args: List[str] = []
    selected_tag: Optional[str] = None
    for i, item in enumerate(items):
        item_id = str(i)
        item_args.append(item_id)

        if isinstance(item, str):
            item_map[item_id] = item
            item_args.append(item)

            if selected_item == item:
                selected_tag = item_id
        else:
            item_map[item_id] = item[0]
            item_args.append(item[1])

            if selected_item == item[0]:
                selected_tag = item_id

    menu_args = menu_args or []
    if selected_tag is not None:
        menu_args.extend(["--default-item", selected_tag])

    result = whiptail(
        "--notags", *menu_args, "--menu", text, HEIGHT, WIDTH, LIST_HEIGHT, *item_args
    )
    return item_map.get(result)


def inputbox(text: str, init: Optional[Any] = None) -> Optional[str]:
    return whiptail("--inputbox", text, HEIGHT, WIDTH, str(init) or "")


def paswordbox(text: str) -> Optional[str]:
    return whiptail("--passwordbox", text, HEIGHT, WIDTH)


def radiolist(
    text: str,
    items: Sequence[ItemType],
    selected_item: Any,
    *args,
) -> Optional[str]:
    assert items, "No items"

    item_map: Dict[str, ItemType] = {}
    item_args: List[str] = []
    for i, item in enumerate(items):
        item_id = str(i)
        item_args.append(item_id)

        if isinstance(item, str):
            item_map[item_id] = item
            item_args.append(item)

            if item == selected_item:
                item_args.append("1")
            else:
                item_args.append("0")
        else:
            item_map[item_id] = item[0]
            item_args.append(item[1])

            if item[0] == selected_item:
                item_args.append("1")
            else:
                item_args.append("0")

    result = whiptail(
        "--notags", *args, "--radiolist", text, HEIGHT, WIDTH, LIST_HEIGHT, *item_args
    )

    if result is None:
        return None

    return item_map.get(result, result)


def checklist(
    text: str,
    items: Sequence[ItemType],
    selected_items: Sequence[Any],
    *args,
) -> List[str]:
    assert items, "No items"

    item_map: Dict[str, ItemType] = {}
    item_args: List[str] = []
    for i, item in enumerate(items):
        item_id = str(i)
        item_args.append(item_id)

        if isinstance(item, str):
            item_map[item_id] = item
            item_args.append(item)

            if item in selected_items:
                item_args.append("1")
            else:
                item_args.append("0")
        else:
            item_map[item_id] = item[0]
            item_args.append(item[1])

            if item[0] in selected_items:
                item_args.append("1")
            else:
                item_args.append("0")

    result = whiptail(
        "--notags", *args, "--checklist", text, HEIGHT, WIDTH, LIST_HEIGHT, *item_args
    )

    if result is None:
        return None

    return [
        item_map.get(result_item, result_item) for result_item in shlex.split(result)
    ]


def yesno(text: str) -> bool:
    return whiptail("--yesno", text, HEIGHT, WIDTH) is not None


def msgbox(text: str) -> None:
    whiptail("--msgbox", text, HEIGHT, WIDTH)


def gauge(text: str, seconds: int, parts: int = 20) -> None:
    proc = subprocess.Popen(
        ["whiptail", "--title", TITLE, "--gauge", text, HEIGHT, WIDTH, "0"],
        stdin=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert proc.stdin is not None

    percent = 0
    while percent <= 100:
        time.sleep(seconds / parts)
        percent += int(100 / parts)
        print(percent, file=proc.stdin, flush=True)

    proc.communicate()


def run_with_gauge(
    text: str, commands: Sequence[Sequence[str]], sudo_password: Optional[str] = None
) -> bool:
    proc = subprocess.Popen(
        ["whiptail", "--title", TITLE, "--gauge", text, HEIGHT, WIDTH, "0"],
        stdin=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert proc.stdin is not None
    percent = 0
    seconds = 5
    parts = 20

    with ThreadPoolExecutor() as executor:
        for command in commands:
            future = executor.submit(_run_command, command, sudo_password)
            while not future.done():
                time.sleep(seconds / parts)
                percent += int(100 / parts)
                if percent > 100:
                    percent = 0

                print(percent, file=proc.stdin, flush=True)

            if not future.result():
                # Error occurred
                return False

    proc.communicate()
    return True


def _run_command(command: Sequence[str], sudo_password: Optional[str] = None) -> bool:
    try:
        assert command
        proc_input: Optional[str] = None
        if (command[0] == "sudo") and (sudo_password is not None):
            proc_input = sudo_password

        proc = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        _stdout, stderr = proc.communicate(proc_input)
        if proc.returncode != 0:
            _LOGGER.error("Error running command: %s", command)
            _LOGGER.error(stderr)
            return False
    except Exception:
        _LOGGER.exception("Error running command: %s", command)
        return False

    return True


def pip_install(*args) -> List[str]:
    return [
        str(_PROGRAM_DIR / ".venv" / "bin" / "pip3"),
        "install",
        "--extra-index-url",
        "https://www.piwheels.org/simple",
        "-f",
        "https://synesthesiam.github.io/prebuilt-apps/",
    ] + list(args)


# -----------------------------------------------------------------------------


if __name__ == "__main__":
    main()
