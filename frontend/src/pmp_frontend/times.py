"""Dates and times as people here read them: entered and shown in Belgian time."""

from datetime import datetime
from zoneinfo import ZoneInfo

BRUSSELS = ZoneInfo("Europe/Brussels")


def local(moment: str) -> datetime:
    return datetime.fromisoformat(moment).astimezone(BRUSSELS)


def shown(moment: str) -> str:
    return local(moment).strftime("%d/%m/%Y %H:%M")


def moment_from(date_text: str, time_text: str) -> str | None:
    """The ISO moment for a date and time in Belgian time, or None if unreadable."""
    try:
        moment = datetime.fromisoformat(f"{date_text}T{time_text}")
    except ValueError:
        return None
    return moment.replace(tzinfo=BRUSSELS).isoformat()
