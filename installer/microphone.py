"""Microphone settings."""
import array
import math
import subprocess
import logging
from concurrent.futures import ThreadPoolExecutor, Future
from typing import Dict, Optional, List

from .const import Settings, RECORD_SECONDS, RECORD_RMS_MIN
from .whiptail import gauge, msgbox, radiolist, menu, inputbox

_LOGGER = logging.getLogger()


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

                gauge("Speak loudly into the microphone.", RECORD_SECONDS)
                for device, future in futures.items():
                    device_rms = future.result()
                    if device_rms < RECORD_RMS_MIN:
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
                str(RECORD_SECONDS),
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
                result = inputbox(
                    "Volume Multipler (1 = default)", settings.mic_volume_multiplier
                )
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
