"""Wake word settings."""
import itertools
import re
import shutil
from pathlib import Path
from typing import Optional, Dict

from .const import Settings, SatelliteType, WakeWordSystem, LOCAL_DIR
from .whiptail import msgbox, menu, radiolist, run_with_gauge, yesno, error


def configure_wake_word(settings: Settings) -> None:
    if settings.satellite_type != SatelliteType.WAKE:
        if not yesno("Set satellite type to local wake word?"):
            return

        settings.satellite_type = SatelliteType.WAKE
        settings.save()

    choice: Optional[str] = None
    while True:
        choice = menu(
            "Main > Wake Word",
            [("system", "Wake Word System"), ("wake_word", "Wake Word")],
            selected_item=choice,
            menu_args=["--ok-button", "Select", "--cancel-button", "Back"],
        )

        if choice == "system":
            wake_word_system = radiolist(
                "Wake Word System:",
                [v.value for v in WakeWordSystem],
                settings.wake_word_system,
            )
            if wake_word_system is None:
                continue

            wake_word_system = WakeWordSystem(wake_word_system)
            install_wake_word(settings, wake_word_system)
        elif choice == "wake_word":
            select_wake_word(settings)
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

        settings.wake_word_system = wake_word_system
        settings.wake_word.setdefault(WakeWordSystem.OPENWAKEWORD, "ok_nabu")
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
            else:
                msgbox("porcupine1 installed successfully")

        settings.wake_word_system = wake_word_system
        settings.save()
        return

    if wake_word_system == WakeWordSystem.SNOWBOY:
        snowboy_dir = LOCAL_DIR / "wyoming-snowboy"
        if not snowboy_dir.exists():
            if not yesno("Install snowboy?"):
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
            else:
                msgbox("snowboy installed successfully")

        settings.wake_word_system = wake_word_system
        settings.save()
        return


def select_wake_word(settings: Settings) -> None:
    if settings.wake_word_system == WakeWordSystem.OPENWAKEWORD:
        oww_dir = LOCAL_DIR / "wyoming-openwakeword"
        if not oww_dir.exists():
            msgbox("openWakeWord is not installed")
            return

        custom_wake_word_dir = (
            LOCAL_DIR / "custom-wake-words" / WakeWordSystem.OPENWAKEWORD.value
        )
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

            items = [("__community__", "Download Community Wake Words")] + list(
                sorted(ww_paths.keys())
            )

            wake_word = radiolist(
                "Wake Word:", items, settings.wake_word.get(WakeWordSystem.OPENWAKEWORD)
            )

            if wake_word is None:
                break

            if wake_word == "__community__":
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
                continue

            wake_word_path = ww_paths[wake_word]
            if wake_word_path.is_relative_to(community_wake_word_dir):
                # Copy to custom directory
                shutil.copy(wake_word_path, custom_wake_word_dir)

            settings.wake_word[WakeWordSystem.OPENWAKEWORD] = wake_word
            settings.save()
            break

        return

    if settings.wake_word_system == WakeWordSystem.PORCUPINE1:
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
            "Wake Word:",
            ww_names,
            settings.wake_word.get(WakeWordSystem.PORCUPINE1),
        )

        if wake_word is not None:
            settings.wake_word[WakeWordSystem.PORCUPINE1] = wake_word
            settings.save()

        return

    if settings.wake_word_system == WakeWordSystem.SNOWBOY:
        snowboy_dir = LOCAL_DIR / "wyoming-snowboy"
        if not snowboy_dir.exists():
            msgbox("snowboy is not installed")
            return

        custom_wake_word_dir = (
            LOCAL_DIR / "custom-wake-words" / WakeWordSystem.SNOWBOY.value
        )
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

        wake_word = radiolist(
            "Wake Word:", ww_names, settings.wake_word.get(WakeWordSystem.SNOWBOY)
        )

        if wake_word is not None:
            settings.wake_word[WakeWordSystem.SNOWBOY] = wake_word
            settings.save()

        return
