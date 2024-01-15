"""Satellite settings."""
from typing import Optional

from .const import SatelliteType, Settings
from .whiptail import error, inputbox, menu, passwordbox, radiolist, run_with_gauge


def configure_satellite(settings: Settings) -> None:
    choice: Optional[str] = None
    while True:
        choice = satellite_menu(choice)

        if choice == "name":
            name = inputbox("Satellite Name:", settings.satellite.name)
            if name:
                settings.satellite.name = name
                settings.save()
        elif choice == "type":
            satellite_type = radiolist(
                "Satellite Type:",
                [
                    (SatelliteType.ALWAYS_STREAMING, "Always streaming"),
                    (SatelliteType.VAD, "Voice activity detection"),
                    (SatelliteType.WAKE, "Local wake word detection"),
                ],
                settings.satellite.type,
            )

            if satellite_type is not None:
                settings.satellite.type = SatelliteType(satellite_type)
                settings.save()
        elif choice in ("stop", "start"):
            password = passwordbox("sudo password:")
            if not password:
                continue

            command = ["sudo", "-S", "systemctl", choice, "wyoming-satellite.service"]
            text = (
                "Stopping satellite..." if choice == "stop" else "Starting satellite..."
            )
            success = run_with_gauge(text, [command], sudo_password=password)
            if not success:
                error(
                    "stopping satellite" if choice == "stop" else "starting satellite"
                )
        elif choice == "debug":
            debug = radiolist(
                "Debug Mode:",
                [
                    ("disabled", "Disabled"),
                    ("enabled", "Enabled"),
                ],
                "enabled" if settings.satellite.debug else "disabled",
            )

            if debug is not None:
                settings.satellite.debug = debug == "enabled"
                settings.save()
        else:
            break


def satellite_menu(last_choice: Optional[str]) -> Optional[str]:
    return menu(
        "Main > Satellite",
        [
            ("name", "Satellite Name"),
            ("type", "Satellite Type"),
            ("stop", "Stop Service"),
            ("start", "Start Service"),
            ("debug", "Set Debug Mode"),
        ],
        selected_item=last_choice,
        menu_args=["--ok-button", "Select", "--cancel-button", "Back"],
    )
