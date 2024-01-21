"""Command-line installer."""
import logging
from typing import List, Optional

from .const import LOCAL_DIR, PROGRAM_DIR, SatelliteType, Settings
from .drivers import install_drivers
from .microphone import configure_microphone
from .packages import (
    can_import,
    install_packages,
    install_packages_nogui,
    packages_installed,
)
from .satellite import configure_satellite
from .services import generate_services, install_services, stop_services
from .speakers import configure_speakers
from .wake_word import configure_wake_word
from .whiptail import ItemType, error, menu, msgbox, passwordbox, run_with_gauge

_LOGGER = logging.getLogger()


def main() -> None:
    LOCAL_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=LOCAL_DIR / "installer.log", filemode="w", level=logging.DEBUG
    )

    settings = Settings.load()

    if not packages_installed("whiptail"):
        install_packages_nogui("whiptail")

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


def apply_settings(settings: Settings) -> None:
    if settings.mic.device is None:
        msgbox("Please configure microphone")
        return

    if (settings.satellite.type == SatelliteType.WAKE) and (
        settings.wake.system is None
    ):
        msgbox("Please set wake word system")
        return

    password: Optional[str] = None
    if not packages_installed("python3-pip", "python3-venv"):
        password = passwordbox("sudo password:")
        if not password:
            return

        success = install_packages(
            "Installing Python packages...", password, "python3-pip", "python3-venv"
        )
        if not success:
            error("installing pip/venv for Python")
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
    if (settings.satellite.type == SatelliteType.VAD) and (
        not can_import("pysilero_vad")
    ):
        result = run_with_gauge(
            "Installing vad...",
            [pip_install("-r", str(PROGRAM_DIR / "requirements_vad.txt"))],
        )
        if not result:
            error("installing vad")
            return

    # webrtc (audio enhancements)
    if ((settings.mic.noise_suppression > 0) or (settings.mic.auto_gain > 0)) and (
        not can_import("webrtc_noise_gain")
    ):
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

    if (
        settings.satellite.event_service_command
        and (
            ("2mic" in settings.satellite.event_service_command)
            or ("4mic" in settings.satellite.event_service_command)
        )
    ) and (not can_import("gpiozero", "spidev")):
        result = run_with_gauge(
            "Installing event requirements...",
            [pip_install("-r", str(PROGRAM_DIR / "requirements_respeaker.txt"))],
        )
        if not result:
            error("installing event requirements")
            return

    generate_services(settings)

    if password is None:
        password = passwordbox("sudo password:")
        if not password:
            return

    stop_services(password)
    install_services(settings, password)


# -----------------------------------------------------------------------------


if __name__ == "__main__":
    main()
