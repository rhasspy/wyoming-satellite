"""Hardware drivers."""
import sys
from typing import Optional

from .const import PROGRAM_DIR, Settings
from .whiptail import error, menu, msgbox, passwordbox, run_with_gauge, yesno


def install_drivers(settings: Settings) -> None:
    choice: Optional[str] = None
    while True:
        choice = menu(
            "Main > Drivers",
            [("respeaker", "Install ReSpeaker Drivers")],
            selected_item=choice,
            menu_args=["--ok-button", "Select", "--cancel-button", "Back"],
        )

        if choice == "respeaker":
            if yesno(
                "ReSpeaker drivers for the Raspberry Pi will now be compiled and installed. "
                "This will take a long time and require a reboot. "
                "Continue?"
            ):
                password = passwordbox("sudo password:")
                success = run_with_gauge(
                    "Installing drivers...",
                    [
                        [
                            "sudo",
                            "-S",
                            str(PROGRAM_DIR / "etc" / "install-respeaker-drivers.sh"),
                        ]
                    ],
                    sudo_password=password,
                )

                if not success:
                    error("installing ReSpeaker drivers")
                    return

                msgbox(
                    "Driver installation complete. "
                    "Please reboot your Raspberry Pi and re-run the installer. "
                    'Once rebooted, select the "seeed" microphone.'
                )

                sys.exit(0)
        else:
            break
