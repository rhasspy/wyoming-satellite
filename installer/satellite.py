"""Satellite settings."""
from typing import Optional

from .const import PROGRAM_DIR, SatelliteType, Settings
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
        elif choice == "feedback":
            configure_feedback(settings)
        elif choice in ("restart", "stop", "start"):
            password = passwordbox("sudo password:")
            if not password:
                continue

            command = ["sudo", "-S", "systemctl", choice, "wyoming-satellite.service"]
            text = {"restart": "Restarting", "stop": "Stopping", "start": "Starting"}[
                choice
            ]
            success = run_with_gauge(
                f"{text} satellite...", [command], sudo_password=password
            )
            if not success:
                error(f"{text.lower()} satellite")
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
            ("feedback", "Feedback"),
            ("restart", "Restart Services"),
            ("stop", "Stop Services"),
            ("start", "Start Services"),
            ("debug", "Set Debug Mode"),
        ],
        selected_item=last_choice,
        menu_args=["--ok-button", "Select", "--cancel-button", "Back"],
    )


def configure_feedback(settings: Settings) -> None:
    choice: Optional[str] = None
    while True:
        choice = menu(
            "Main > Satellite > Feedback",
            [("respeaker", "ReSpeaker")],
            menu_args=["--ok-button", "Select", "--cancel-button", "Back"],
        )
        if choice == "respeaker":
            selected_service: Optional[str] = None
            if settings.satellite.event_service_command:
                if "2mic" in settings.satellite.event_service_command[0]:
                    selected_service = "2mic"
                elif "4mic" in settings.satellite.event_service_command[0]:
                    selected_service = "4mic"

            event_service = radiolist(
                "Event Service:",
                [
                    ("none", "None"),
                    ("2mic", "2mic LEDs"),
                    ("4mic", "4mic LEDs"),
                ],
                selected_service,
            )

            if event_service is not None:
                if event_service == "none":
                    settings.satellite.event_service_command = None
                else:
                    settings.satellite.event_service_command = [
                        str(PROGRAM_DIR / "script" / f"run_{event_service}"),
                        "--uri",
                        "tcp://127.0.0.1:10500",
                    ]

                settings.save()
        else:
            break
