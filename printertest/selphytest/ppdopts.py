"""PPD option discovery and validation.

All supported option keywords, choices and defaults are read from the PPD that
CUPS holds for the queue — nothing about the CP1500 is hardcoded here.
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager

from . import cups_module

log = logging.getLogger("selphytest.ppd")

# PPD attributes that identify driver and model
IDENT_ATTRIBUTES = ["NickName", "ModelName", "ShortNickName", "FileVersion",
                    "StpDriverVersion", "Manufacturer", "PCFileName"]


@contextmanager
def open_ppd(conn, printer: str):
    """Yield a parsed cups.PPD for the queue; the temp file is cleaned up after."""
    cups = cups_module()
    try:
        path = conn.getPPD(printer)
    except cups.IPPError as exc:
        raise SystemExit(
            f"ERROR: cannot fetch PPD for queue '{printer}': {exc}. "
            "Is this a raw queue (created without -m driver)?"
        )
    try:
        ppd = cups.PPD(path)
        ppd.markDefaults()
        yield ppd
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def identity(ppd) -> dict[str, str]:
    """Driver/model identification attributes from the PPD."""
    result = {}
    for name in IDENT_ATTRIBUTES:
        attr = ppd.findAttr(name)
        if attr is not None and attr.value:
            result[name] = attr.value
    return result


def all_options(ppd) -> list[dict]:
    """Flatten every UI option of the PPD into dicts.

    Each entry: {group, keyword, text, default, choices: [(choice, text), ...]}
    """
    options = []
    for group in ppd.optionGroups:
        _collect_group(group, group.text or group.name, options)
    return options


def _collect_group(group, group_label: str, sink: list[dict]) -> None:
    for option in group.options:
        sink.append(
            {
                "group": group_label,
                "keyword": option.keyword,
                "text": option.text or option.keyword,
                "default": option.defchoice,
                "choices": [
                    (choice["choice"], choice.get("text", choice["choice"]))
                    for choice in option.choices
                ],
            }
        )
    for sub in getattr(group, "subgroups", []) or []:
        _collect_group(sub, f"{group_label} / {sub.text or sub.name}", sink)


def find_option(ppd, keyword: str):
    """Case-insensitive lookup of a PPD option by keyword."""
    option = ppd.findOption(keyword)
    if option is not None:
        return option
    for entry in all_options(ppd):
        if entry["keyword"].lower() == keyword.lower():
            return ppd.findOption(entry["keyword"])
    return None


def option_choices(ppd, keyword: str) -> list[str] | None:
    option = find_option(ppd, keyword)
    if option is None:
        return None
    return [choice["choice"] for choice in option.choices]


def option_default(ppd, keyword: str) -> str | None:
    option = find_option(ppd, keyword)
    return option.defchoice if option is not None else None


def validate_options(ppd, options: dict[str, str]) -> list[str]:
    """Check user-supplied option values against the PPD.

    Returns a list of problem strings (empty == fine). Non-PPD options such as
    fit-to-page / print-scaling are CUPS filter options and are passed through.
    """
    problems = []
    for keyword, value in options.items():
        option = find_option(ppd, keyword)
        if option is None:
            log.debug("option %s not in PPD — assuming CUPS filter option", keyword)
            continue
        choices = [choice["choice"] for choice in option.choices]
        if value not in choices:
            # PPD booleans accept True/False in any case
            lowered = {c.lower(): c for c in choices}
            if value.lower() in lowered:
                continue
            problems.append(
                f"{keyword}={value} is not a supported choice. "
                f"Supported: {', '.join(choices)}"
            )
    return problems


def conflict_count(ppd, options: dict[str, str]) -> int:
    """Mark the given PPD options and return the number of UI constraint conflicts."""
    ppd.markDefaults()
    for keyword, value in options.items():
        option = find_option(ppd, keyword)
        if option is None:
            continue
        choices = {c["choice"].lower(): c["choice"] for c in option.choices}
        actual = choices.get(value.lower(), value)
        try:
            ppd.markOption(option.keyword, actual)
        except Exception as exc:
            log.debug("markOption(%s=%s) failed: %s", keyword, actual, exc)
    try:
        return ppd.conflicts()
    except Exception as exc:
        log.debug("ppd.conflicts() failed: %s", exc)
        return 0
