"""Install system packages."""
import logging
import subprocess

from .const import PROGRAM_DIR
from .whiptail import run_with_gauge

_LOGGER = logging.getLogger()


def packages_installed(*packages) -> bool:
    for package in packages:
        try:
            subprocess.check_call(
                ["dpkg", "--status", str(package)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            return False

    return True


def install_packages_nogui(*packages, update: bool = True) -> bool:
    assert packages, "No packages"

    commands = []
    if update:
        commands.append(["sudo", "apt-get", "update"])

    commands.append(
        ["sudo", "apt-get", "install", "--yes"] + [str(p) for p in packages]
    )

    try:
        for command in commands:
            subprocess.check_call(
                command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
    except Exception:
        _LOGGER.exception("Unexpected error installing packages: %s", packages)
        return False

    return True


def install_packages(
    text: str, sudo_password: str, *packages, update: bool = True
) -> bool:
    assert packages, "No packages"

    commands = []
    if update:
        commands.append(["sudo", "-S", "apt-get", "update"])

    commands.append(
        ["sudo", "-S", "apt-get", "install", "--yes"] + [str(p) for p in packages]
    )

    return run_with_gauge(text, commands, sudo_password=sudo_password)


def can_import(*names) -> bool:
    assert names, "No names"

    venv_dir = PROGRAM_DIR / ".venv"
    if not venv_dir.exists():
        return False

    try:
        import venv
    except ImportError:
        return False

    context = venv.EnvBuilder().ensure_directories(PROGRAM_DIR / ".venv")

    try:
        subprocess.check_call(
            [context.env_exe, "-c", "; ".join(f"import {name}" for name in names)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        return False

    return True
