"""Wake word settings."""
import itertools
import re
import shutil
from pathlib import Path
from typing import Dict, Optional

from .const import LOCAL_DIR, SatelliteType, Settings, WakeWordSystem
from .packages import install_packages, packages_installed
from .whiptail import (
    error,
    inputbox,
    menu,
    msgbox,
    passwordbox,
    radiolist,
    run_with_gauge,
    yesno,
)


def configure_wake_word(settings: Settings) -> None:
    if settings.satellite.type != SatelliteType.WAKE:
        if not yesno("Set satellite type to local wake word?"):
            return

        settings.satellite.type = SatelliteType.WAKE
        settings.save()

    def star(ww_system: WakeWordSystem) -> str:
        return (
            f"{ww_system.value} [*]"
            if settings.wake.system == ww_system
            else ww_system.value
        )

    choice: Optional[str] = None
    while True:
        choice = menu(
            "Main > Wake Word",
            [
                ("system", "Wake Word System"),
                ("wake_word", "Choose Wake Word"),
                ("openWakeWord", star(WakeWordSystem.OPENWAKEWORD)),
                ("porcupine1", star(WakeWordSystem.PORCUPINE1)),
                ("snowboy", star(WakeWordSystem.SNOWBOY)),
            ],
            selected_item=choice,
            menu_args=["--ok-button", "Select", "--cancel-button", "Back"],
        )

        if choice == "system":
            wake_word_system = radiolist(
                "Wake Word System:",
                [v.value for v in WakeWordSystem],
                settings.wake.system,
            )
            if wake_word_system is None:
                continue

            wake_word_system = WakeWordSystem(wake_word_system)
            install_wake_word(settings, wake_word_system)
        elif choice == "wake_word":
            select_wake_word(settings)
        elif choice == "openWakeWord":
            configure_openWakeWord(settings)
        elif choice == "porcupine1":
            configure_porcupine1(settings)
        elif choice == "snowboy":
            configure_snowboy(settings)
        else:
            break


def install_wake_word(settings: Settings, wake_word_system: WakeWordSystem) -> None:
    if wake_word_system == WakeWordSystem.OPENWAKEWORD:
        oww_dir = LOCAL_DIR / "wyoming-openwakeword"
        if not oww_dir.exists():
            if not yesno("Install openWakeWord?"):
                return

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

            if not success:
                # Clean up
                try:
                    shutil.rmtree(oww_dir)
                except Exception:
                    pass

                error("installing openWakeWord")
                return

        msgbox("openWakeWord installed successfully")
        settings.wake.system = wake_word_system
        settings.save()
        return

    if wake_word_system == WakeWordSystem.PORCUPINE1:
        porcupine1_dir = LOCAL_DIR / "wyoming-porcupine1"
        if not porcupine1_dir.exists():
            if not yesno("Install porcupine1?"):
                return

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

            if not success:
                # Clean up
                try:
                    shutil.rmtree(porcupine1_dir)
                except Exception:
                    pass

                error("installing porcupine1")
                return

        msgbox("porcupine1 installed successfully")
        settings.wake.system = wake_word_system
        settings.save()
        return

    if wake_word_system == WakeWordSystem.SNOWBOY:
        snowboy_dir = LOCAL_DIR / "wyoming-snowboy"
        if not snowboy_dir.exists():
            if not yesno("Install snowboy?"):
                return

            snowboy_packages = ["python3-dev", "swig", "libatlas-base-dev"]
            if not packages_installed(*snowboy_packages):
                password = passwordbox("sudo password:")
                if not password:
                    return

                success = install_packages(
                    "Installing system packages...", password, *snowboy_packages
                )
                if not success:
                    error("installing " + ", ".join(snowboy_packages))
                    return

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

            if not success:
                # Clean up
                try:
                    shutil.rmtree(snowboy_dir)
                except Exception:
                    pass

                error("installing snowboy")
                return

        msgbox("snowboy installed successfully")
        settings.wake.system = wake_word_system
        settings.save()
        return


def select_wake_word(settings: Settings) -> None:
    if settings.wake.system == WakeWordSystem.OPENWAKEWORD:
        oww_dir = LOCAL_DIR / "wyoming-openwakeword"
        if not oww_dir.exists():
            msgbox("openWakeWord is not installed")
            return

        custom_wake_word_dir = LOCAL_DIR / "custom-wake-words" / "openWakeWord"
        custom_wake_word_dir.mkdir(parents=True, exist_ok=True)

        community_wake_word_dir = LOCAL_DIR / "home-assistant-wakewords-collection"

        while True:
            ww_paths: Dict[str, Path] = {
                p.stem: p for p in custom_wake_word_dir.glob("*.tflite")
            }

            for ww_path in community_wake_word_dir.rglob("*.tflite"):
                ww_name = ww_path.stem
                if ww_name in ww_paths:
                    continue

                ww_paths[ww_name] = ww_path

            for ww_path in (oww_dir / "wyoming_openwakeword" / "models").glob(
                "*.tflite"
            ):
                if not re.match("^.+_v[0-9].*$", ww_path.stem):
                    continue

                ww_name = ww_path.stem.rsplit("_", maxsplit=1)[0]
                if ww_name in ww_paths:
                    continue

                ww_paths[ww_name] = ww_path

            items = sorted(list(ww_paths.keys()))
            wake_word = radiolist(
                "Wake Word:", items, settings.wake.openwakeword.wake_word
            )
            if wake_word is None:
                break

            wake_word_path = ww_paths[wake_word]
            if wake_word_path.is_relative_to(community_wake_word_dir):
                # Copy to custom directory
                shutil.copy(wake_word_path, custom_wake_word_dir)

            settings.wake.openwakeword.wake_word = wake_word
            settings.save()
            break

        return

    if settings.wake.system == WakeWordSystem.PORCUPINE1:
        porcupine1_dir = LOCAL_DIR / "wyoming-porcupine1"
        if not porcupine1_dir.exists():
            msgbox("porcupine1 is not installed")
            return

        ww_names = sorted(
            list(
                set(
                    p.stem.rsplit("_", maxsplit=1)[0]
                    for p in (
                        porcupine1_dir / "wyoming_porcupine1" / "data" / "resources"
                    ).rglob("*.ppn")
                )
            )
        )

        wake_word = radiolist(
            "Wake Word:", ww_names, settings.wake.porcupine1.wake_word
        )
        if wake_word is not None:
            settings.wake.porcupine1.wake_word = wake_word
            settings.save()

        return

    if settings.wake.system == WakeWordSystem.SNOWBOY:
        snowboy_dir = LOCAL_DIR / "wyoming-snowboy"
        if not snowboy_dir.exists():
            msgbox("snowboy is not installed")
            return

        custom_wake_word_dir = LOCAL_DIR / "custom-wake-words" / "snowboy"
        custom_wake_word_dir.mkdir(parents=True, exist_ok=True)

        builtin_wake_words = (snowboy_dir / "wyoming_snowboy" / "data").glob("*.umdl")
        custom_wake_words = itertools.chain(
            custom_wake_word_dir.glob("*.pmdl"), custom_wake_word_dir.glob("*.umdl")
        )
        ww_names = sorted(
            list(
                set(
                    p.stem
                    for p in itertools.chain(builtin_wake_words, custom_wake_words)
                )
            )
        )

        wake_word = radiolist("Wake Word:", ww_names, settings.wake.snowboy.wake_word)
        if wake_word is not None:
            settings.wake.snowboy.wake_word = wake_word
            settings.save()

        return


def configure_openWakeWord(settings: Settings) -> None:
    choice: Optional[str] = None
    while True:
        choice = menu(
            "Main > Wake Word > openWakeWord",
            [
                ("community", "Download Community Wake Words"),
                ("threshold", "Set Threshold"),
                ("trigger_level", "Set Trigger Level"),
            ],
            selected_item=choice,
            menu_args=["--ok-button", "Select", "--cancel-button", "Back"],
        )

        if choice == "community":
            community_wake_word_dir = LOCAL_DIR / "home-assistant-wakewords-collection"

            if not community_wake_word_dir.exists():
                success = run_with_gauge(
                    "Downloading community wake words...",
                    [
                        [
                            "git",
                            "clone",
                            "https://github.com/fwartner/home-assistant-wakewords-collection.git",
                            str(community_wake_word_dir),
                        ]
                    ],
                )

                if not success:
                    error("downloading community wake words")
            else:
                success = run_with_gauge(
                    "Updating community wake words...",
                    [
                        [
                            "git",
                            "-C",
                            str(community_wake_word_dir),
                            "pull",
                            "origin",
                            "main",
                        ]
                    ],
                )

                if not success:
                    error("updating community wake words")
        elif choice == "threshold":
            while True:
                threshold = inputbox(
                    "Threshold (0-1, 0.5 = default):",
                    settings.wake.openwakeword.threshold,
                )
                if threshold is None:
                    break

                try:
                    threshold_float = float(threshold)
                except ValueError:
                    msgbox("Invalid value")
                    continue

                if 0 < threshold_float < 1:
                    settings.wake.openwakeword.threshold = threshold_float
                    settings.save()
                    break

                msgbox("Threshold must be in (0, 1)")
        elif choice == "trigger_level":
            while True:
                trigger_level = inputbox(
                    "Trigger Level (> 0, 1 = default):",
                    settings.wake.openwakeword.trigger_level,
                )
                if trigger_level is None:
                    break

                try:
                    trigger_level_int = int(trigger_level)
                except ValueError:
                    msgbox("Invalid value")
                    continue

                if trigger_level_int > 0:
                    settings.wake.openwakeword.trigger_level = trigger_level_int
                    settings.save()
                    break

                msgbox("Trigger level must be > 0")
        else:
            break


def configure_porcupine1(settings: Settings) -> None:
    choice: Optional[str] = None
    while True:
        choice = menu(
            "Main > Wake Word > porcupine1",
            [
                ("sensitivity", "Set Sensitivity"),
            ],
            selected_item=choice,
            menu_args=["--ok-button", "Select", "--cancel-button", "Back"],
        )

        if choice == "sensitivity":
            while True:
                sensitivity = inputbox(
                    "Sensitivity (0-1, 0.5 = default):",
                    settings.wake.porcupine1.sensitivity,
                )
                if sensitivity is None:
                    break

                try:
                    sensitivity_float = float(sensitivity)
                except ValueError:
                    msgbox("Invalid value")
                    continue

                if 0 < sensitivity_float < 1:
                    settings.wake.porcupine1.sensitivity = sensitivity_float
                    settings.save()
                    break

                msgbox("Sensitivity must be in (0, 1)")
        else:
            break


def configure_snowboy(settings: Settings) -> None:
    choice: Optional[str] = None
    while True:
        choice = menu(
            "Main > Wake Word > snowboy",
            [
                ("sensitivity", "Set Sensitivity"),
            ],
            selected_item=choice,
            menu_args=["--ok-button", "Select", "--cancel-button", "Back"],
        )

        if choice == "sensitivity":
            while True:
                sensitivity = inputbox(
                    "Sensitivity (0-1, 0.5 = default):",
                    settings.wake.snowboy.sensitivity,
                )
                if sensitivity is None:
                    break

                try:
                    sensitivity_float = float(sensitivity)
                except ValueError:
                    msgbox("Invalid value")
                    continue

                if 0 < sensitivity_float < 1:
                    settings.wake.snowboy.sensitivity = sensitivity_float
                    settings.save()
                    break

                msgbox("Sensitivity must be in (0, 1)")
        else:
            break
