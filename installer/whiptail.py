"""Python interface to whiptail command."""
import logging
import shlex
import subprocess
import time
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Tuple, Union

from .const import HEIGHT, LIST_HEIGHT, TITLE, WIDTH

ItemType = Union[str, Tuple[Any, str]]

_LOGGER = logging.getLogger()


def whiptail(*args) -> Optional[str]:
    proc = subprocess.Popen(
        ["whiptail", "--title", TITLE] + list(args),
        stderr=subprocess.PIPE,
    )

    _stdout, stderr = proc.communicate()
    if proc.returncode != 0:
        return None

    return stderr.decode("utf-8")


def menu(
    text: str,
    items: Sequence[ItemType],
    selected_item: Optional[str] = None,
    menu_args: Optional[Sequence[str]] = None,
) -> Optional[str]:
    assert items, "No items"

    item_map: Dict[Optional[str], str] = {}
    item_args: List[str] = []
    selected_tag: Optional[str] = None
    for i, item in enumerate(items):
        item_id = str(i)
        item_args.append(item_id)

        if isinstance(item, str):
            item_map[item_id] = item
            item_args.append(item)

            if selected_item == item:
                selected_tag = item_id
        else:
            item_map[item_id] = item[0]
            item_args.append(item[1])

            if selected_item == item[0]:
                selected_tag = item_id

    menu_args = list(menu_args) if menu_args is not None else []
    if selected_tag is not None:
        menu_args.extend(["--default-item", selected_tag])

    result = whiptail(
        "--notags", *menu_args, "--menu", text, HEIGHT, WIDTH, LIST_HEIGHT, *item_args
    )
    return item_map.get(result)


def inputbox(text: str, init: Optional[Any] = None) -> Optional[str]:
    return whiptail(
        "--inputbox", text, HEIGHT, WIDTH, str(init) if init is not None else ""
    )


def passwordbox(text: str) -> Optional[str]:
    return whiptail("--passwordbox", text, HEIGHT, WIDTH)


def radiolist(
    text: str,
    items: Sequence[ItemType],
    selected_item: Any,
    *args,
) -> Optional[Any]:
    assert items, "No items"

    item_map: Dict[str, ItemType] = {}
    item_args: List[str] = []
    for i, item in enumerate(items):
        item_id = str(i)
        item_args.append(item_id)

        if isinstance(item, str):
            item_map[item_id] = item
            item_args.append(item)

            if item == selected_item:
                item_args.append("1")
            else:
                item_args.append("0")
        else:
            item_map[item_id] = item[0]
            item_args.append(item[1])

            if item[0] == selected_item:
                item_args.append("1")
            else:
                item_args.append("0")

    result = whiptail(
        "--notags", *args, "--radiolist", text, HEIGHT, WIDTH, LIST_HEIGHT, *item_args
    )

    if result is None:
        return None

    return item_map.get(result, result)


def checklist(
    text: str,
    items: Sequence[ItemType],
    selected_items: Sequence[Any],
    *args,
) -> Optional[List[Any]]:
    assert items, "No items"

    item_map: Dict[str, ItemType] = {}
    item_args: List[str] = []
    for i, item in enumerate(items):
        item_id = str(i)
        item_args.append(item_id)

        if isinstance(item, str):
            item_map[item_id] = item
            item_args.append(item)

            if item in selected_items:
                item_args.append("1")
            else:
                item_args.append("0")
        else:
            item_map[item_id] = item[0]
            item_args.append(item[1])

            if item[0] in selected_items:
                item_args.append("1")
            else:
                item_args.append("0")

    result = whiptail(
        "--notags", *args, "--checklist", text, HEIGHT, WIDTH, LIST_HEIGHT, *item_args
    )

    if result is None:
        return None

    return [
        item_map.get(result_item, result_item) for result_item in shlex.split(result)
    ]


def yesno(text: str) -> bool:
    return whiptail("--yesno", text, HEIGHT, WIDTH) is not None


def msgbox(text: str) -> None:
    whiptail("--msgbox", text, HEIGHT, WIDTH)


def gauge(text: str, seconds: int, parts: int = 20) -> None:
    proc = subprocess.Popen(
        ["whiptail", "--title", TITLE, "--gauge", text, HEIGHT, WIDTH, "0"],
        stdin=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert proc.stdin is not None

    percent = 0
    while percent <= 100:
        time.sleep(seconds / parts)
        percent += int(100 / parts)
        print(percent, file=proc.stdin, flush=True)

    proc.communicate()


def error(reason: str) -> None:
    msgbox(
        f"An error occurred while {reason}.\n" "See local/installer.log for details."
    )


# -----------------------------------------------------------------------------


def run_with_gauge(
    text: str, commands: Sequence[Sequence[str]], sudo_password: Optional[str] = None
) -> bool:
    proc = subprocess.Popen(
        ["whiptail", "--title", TITLE, "--gauge", text, HEIGHT, WIDTH, "0"],
        stdin=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert proc.stdin is not None
    percent = 0
    seconds = 5
    parts = 20

    with ThreadPoolExecutor() as executor:
        for command in commands:
            future = executor.submit(_run_command, command, sudo_password)
            while not future.done():
                time.sleep(seconds / parts)
                percent += int(100 / parts)
                if percent > 100:
                    percent = 0

                print(percent, file=proc.stdin, flush=True)

            if not future.result():
                # Error occurred
                return False

    proc.communicate()
    return True


def _run_command(command: Sequence[str], sudo_password: Optional[str] = None) -> bool:
    try:
        assert command
        proc_input: Optional[str] = None
        if (command[0] == "sudo") and (sudo_password is not None):
            proc_input = sudo_password

        proc = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        _stdout, stderr = proc.communicate(proc_input)
        if proc.returncode != 0:
            _LOGGER.error("Error running command: %s", command)
            _LOGGER.error(stderr)
            return False
    except Exception:
        _LOGGER.exception("Error running command: %s", command)
        return False

    return True
