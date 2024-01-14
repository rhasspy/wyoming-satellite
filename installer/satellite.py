"""Satellite settings."""
from typing import Optional

from .const import Settings, SatelliteType
from .whiptail import menu, inputbox, radiolist, run_with_gauge


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
            ("name", "Satellite Name"),
            ("type", "Satellite Type"),
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

    if satellite_type is not None:
        settings.satellite_type = SatelliteType(satellite_type)
        settings.save()
