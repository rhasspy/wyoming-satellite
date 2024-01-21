"""Microphone settings."""
import array
import logging
import math
import subprocess
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Dict, List, Optional

from .const import RECORD_RMS_MIN, RECORD_SECONDS, Settings
from .whiptail import gauge, inputbox, menu, msgbox, radiolist

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
                    if device_rms is None:
                        _LOGGER.warning("Failed to record from microphone %s", device)
                        continue

                    _LOGGER.debug(
                        "Microphone %s got RMS %s (min: %s)",
                        device,
                        device_rms,
                        RECORD_RMS_MIN,
                    )
                    if device_rms < RECORD_RMS_MIN:
                        continue

                    if (best_rms is None) or (device_rms > best_rms):
                        best_device = device
                        best_rms = device_rms

            if best_device is not None:
                msgbox(f"Successfully detected microphone: {best_device}")
                settings.mic.device = best_device
                settings.save()
            else:
                msgbox(
                    "Audio was not detected from any microphone.\n"
                    "If a satellite is currently running, you may need to stop it."
                )
        elif choice == "list":
            # arecord -L
            microphone_device = radiolist(
                "Select ALSA Device:", get_microphone_devices(), settings.mic.device
            )
            if microphone_device:
                settings.mic.device = microphone_device
                settings.save()
        elif choice == "manual":
            microphone_device = inputbox("Enter ALSA Device:", settings.mic.device)
            if microphone_device:
                settings.mic.device = microphone_device
                settings.save()
        elif choice == "settings":
            configure_audio_settings(settings)
        else:
            break


def microphone_menu(last_choice: Optional[str]) -> Optional[str]:
    return menu(
        "Main > Microphone",
        [
            ("detect", "Autodetect"),
            ("list", "Select From List"),
            ("manual", "Enter Manually"),
            ("settings", "Audio Settings"),
        ],
        selected_item=last_choice,
        menu_args=["--ok-button", "Select", "--cancel-button", "Back"],
    )


def get_microphone_devices() -> List[str]:
    devices = []
    lines = subprocess.check_output(["arecord", "-L"]).decode("utf-8").splitlines()
    for line in lines:
        line = line.strip()

        # default = PulseAudio
        if (line == "default") or line.startswith("plughw:"):
            devices.append(line)

    return devices


def _record_proc(device: str) -> Optional[float]:
    try:
        proc = subprocess.Popen(
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
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        audio, stderr = proc.communicate()
        if proc.returncode != 0:
            _LOGGER.error(
                "Error recording from device %s: %s", device, stderr.decode("utf-8")
            )
            return None

        # 16-bit mono
        audio_array = array.array("h", audio)
        rms = math.sqrt(
            (1 / len(audio_array) * sum(x * x for x in audio_array.tolist()))
        )
        return rms
    except Exception:
        _LOGGER.exception("Error recording from device: %s", device)
        return None

    return 0


def configure_audio_settings(settings: Settings) -> None:
    choice: Optional[str] = None
    while True:
        choice = audio_settings_menu(choice)

        if choice == "noise":
            noise_suppression = radiolist(
                "Noise Suppression Level",
                [(0, "Off"), (1, "Low"), (2, "Medium"), (3, "High"), (4, "Maximum")],
                settings.mic.noise_suppression,
            )
            if noise_suppression is not None:
                settings.mic.noise_suppression = noise_suppression
                settings.save()
        elif choice == "gain":
            while True:
                auto_gain = inputbox("Auto Gain (0-31 dbFS)", settings.mic.auto_gain)
                if auto_gain is None:
                    break

                try:
                    auto_gain_int = int(auto_gain)
                except ValueError:
                    msgbox("Invalid value")
                    continue

                if 0 <= auto_gain_int <= 31:
                    settings.mic.auto_gain = auto_gain_int
                    settings.save()
                    break

                msgbox("Must be 0-31")
        elif choice == "multiplier":
            while True:
                volume_multiplier = inputbox(
                    "Volume Multiplier (1 = default)", settings.mic.volume_multiplier
                )
                if volume_multiplier is None:
                    break

                try:
                    volume_multiplier_float = float(volume_multiplier)
                except ValueError:
                    msgbox("Invalid value")
                    continue

                if volume_multiplier_float > 0:
                    settings.mic.volume_multiplier = volume_multiplier_float
                    settings.save()
                    break

                msgbox("Must be > 0")
        else:
            break


def audio_settings_menu(last_choice: Optional[str]) -> Optional[str]:
    return menu(
        "Main > Microphone > Audio Settings",
        [
            ("noise", "Noise Suppression"),
            ("gain", "Auto Gain"),
            ("multiplier", "Volume Multiplier"),
        ],
        selected_item=last_choice,
        menu_args=["--ok-button", "Select", "--cancel-button", "Back"],
    )
