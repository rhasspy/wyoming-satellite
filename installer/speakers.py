"""Speaker settings."""
import subprocess
import logging
from typing import Optional, List

from .const import Settings, PROGRAM_DIR
from .whiptail import radiolist, inputbox, msgbox, checklist, menu

_LOGGER = logging.getLogger()


def configure_speakers(settings: Settings) -> None:
    choice: Optional[str] = None
    while True:
        choice = speakers_menu(choice)

        if choice == "test":
            sound_device = test_speakers()
            if sound_device is not None:
                settings.sound_device = sound_device
                settings.save()
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


def speakers_menu(last_choice: Optional[str]) -> Optional[str]:
    return menu(
        "Main > Speakers",
        [
            ("test", "Test Speakers"),
            ("list", "Select From List"),
            ("manual", "Enter Manually"),
            ("disable", "Disable Sound"),
            ("feedback", "Toggle Feedback Sounds"),
        ],
        selected_item=last_choice,
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


def test_speakers() -> Optional[str]:
    devices = get_sound_devices()
    if not devices:
        msgbox("No speakers found")
        return None

    device = devices.pop()

    while True:
        choice = menu(
            f"Device: {device}",
            [
                ("play", "Play Sound"),
                ("next", "Next Device"),
                ("choose", "Choose This Device"),
            ],
        )

        if choice == "play":
            test_sound_device(device)
        elif choice == "next":
            if not devices:
                msgbox("No more devices")
                break

            device = devices.pop()
        elif choice == "choose":
            return device
        else:
            break

    return None


def test_sound_device(device: str) -> None:
    try:
        subprocess.check_call(
            ["aplay", "-q", "-D", device, str(PROGRAM_DIR / "sounds" / "awake.wav")]
        )
    except Exception:
        _LOGGER.exception("Error testing device: %s", device)
