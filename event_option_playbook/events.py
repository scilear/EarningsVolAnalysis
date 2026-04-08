"""Generic event-domain objects for the event options engine."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Mapping


class EventFamily(StrEnum):
    """Top-level event families supported by the engine."""

    EARNINGS = "earnings"
    MACRO = "macro"
    OTHER = "other"


class EventTiming(StrEnum):
    """Relative event timing semantics for entry and evaluation windows."""

    PRE_EVENT = "pre_event"
    EVENT_DAY = "event_day"
    POST_EVENT = "post_event"


def normalize_event_timing(value: str | EventTiming) -> EventTiming:
    """Normalize a string or enum value into EventTiming."""

    if isinstance(value, EventTiming):
        return value
    if not isinstance(value, str):
        raise TypeError(
            "Event timing must be a string or EventTiming, "
            f"got {type(value).__name__}."
        )

    normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "pre": EventTiming.PRE_EVENT,
        "pre_event": EventTiming.PRE_EVENT,
        "event": EventTiming.EVENT_DAY,
        "event_day": EventTiming.EVENT_DAY,
        "post": EventTiming.POST_EVENT,
        "post_event": EventTiming.POST_EVENT,
    }
    if normalized not in aliases:
        raise ValueError(
            f"Unsupported event timing '{value}'. "
            "Expected one of: pre_event, event_day, post_event."
        )
    return aliases[normalized]


def normalize_event_family(value: str | EventFamily) -> EventFamily:
    """Normalize a string or enum value into an EventFamily."""

    if isinstance(value, EventFamily):
        return value
    if not isinstance(value, str):
        raise TypeError(
            "Event family must be a string or EventFamily, "
            f"got {type(value).__name__}."
        )

    normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "earnings": EventFamily.EARNINGS,
        "macro": EventFamily.MACRO,
        "other": EventFamily.OTHER,
    }
    if normalized not in aliases:
        raise ValueError(
            f"Unsupported event family '{value}'. "
            "Expected one of: earnings, macro, other."
        )
    return aliases[normalized]


def normalize_event_name(value: str) -> str:
    """Normalize and validate an event name distinct from top-level family labels."""

    if not isinstance(value, str):
        raise TypeError(f"Event name must be a string, got {type(value).__name__}.")
    normalized = value.strip().lower().replace(" ", "_")
    while "__" in normalized:
        normalized = normalized.replace("__", "_")
    normalized = normalized.strip("_-")
    if not normalized:
        raise ValueError("EventSpec.name must be non-empty.")
    if any(char not in "abcdefghijklmnopqrstuvwxyz0123456789_-" for char in normalized):
        raise ValueError(
            "EventSpec.name must contain only lowercase letters, numbers, "
            "underscores, spaces, or hyphens."
        )
    if normalized in {member.value for member in EventFamily}:
        raise ValueError(
            f"EventSpec.name '{value}' is too generic; use a specific event label "
            "(e.g., 'q1_earnings', 'cpi', 'fomc')."
        )
    return normalized


@dataclass(frozen=True)
class EventWindow:
    """Allowed entry or evaluation window relative to the event."""

    timing: EventTiming | str
    start_days: int
    end_days: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "timing", normalize_event_timing(self.timing))

        if isinstance(self.start_days, bool) or not isinstance(self.start_days, int):
            raise TypeError("EventWindow.start_days must be an integer.")
        if isinstance(self.end_days, bool) or not isinstance(self.end_days, int):
            raise TypeError("EventWindow.end_days must be an integer.")
        if self.start_days > self.end_days:
            raise ValueError(
                "EventWindow start_days must be less than or equal to end_days."
            )
        if self.timing == EventTiming.PRE_EVENT and self.end_days > 0:
            raise ValueError(
                "PRE_EVENT windows must end on or before the event day (end_days <= 0)."
            )
        if self.timing == EventTiming.EVENT_DAY and (
            self.start_days != 0 or self.end_days != 0
        ):
            raise ValueError("EVENT_DAY windows must have start_days == 0 and end_days == 0.")
        if self.timing == EventTiming.POST_EVENT and self.start_days < 0:
            raise ValueError(
                "POST_EVENT windows must start on or after the event day (start_days >= 0)."
            )

    def to_dict(self) -> dict[str, Any]:
        """Serialize the window for storage or reporting."""

        return {
            "timing": self.timing.value,
            "start_days": self.start_days,
            "end_days": self.end_days,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> EventWindow:
        """Build an EventWindow from a mapping payload."""

        return cls(
            timing=payload["timing"],
            start_days=int(payload["start_days"]),
            end_days=int(payload["end_days"]),
        )


def default_entry_windows() -> tuple[EventWindow, ...]:
    """Default generic entry/evaluation windows around an event."""

    return (
        EventWindow(timing=EventTiming.PRE_EVENT, start_days=-10, end_days=-1),
        EventWindow(timing=EventTiming.EVENT_DAY, start_days=0, end_days=0),
        EventWindow(timing=EventTiming.POST_EVENT, start_days=1, end_days=5),
    )


@dataclass(frozen=True)
class EventSchedule:
    """Calendar schedule and timeline semantics attached to an event."""

    event_date: dt.date
    event_time_label: str | None = None
    entry_windows: tuple[EventWindow, ...] = ()

    def __post_init__(self) -> None:
        event_date = self.event_date
        if isinstance(event_date, dt.datetime):
            event_date = event_date.date()
            object.__setattr__(self, "event_date", event_date)
        if not isinstance(event_date, dt.date):
            raise TypeError("EventSchedule.event_date must be a datetime.date.")

        if self.event_time_label is not None:
            label = self.event_time_label.strip()
            if not label:
                raise ValueError("EventSchedule.event_time_label cannot be blank.")
            object.__setattr__(self, "event_time_label", label)

        if not self.entry_windows:
            object.__setattr__(self, "entry_windows", default_entry_windows())
        else:
            timings_seen: set[EventTiming] = set()
            normalized: list[EventWindow] = []
            for window in self.entry_windows:
                if not isinstance(window, EventWindow):
                    raise TypeError(
                        "EventSchedule.entry_windows must contain only "
                        "EventWindow items."
                    )
                if window.timing in timings_seen:
                    raise ValueError(
                        f"Duplicate timing '{window.timing.value}' in EventSchedule.entry_windows."
                    )
                timings_seen.add(window.timing)
                normalized.append(window)
            object.__setattr__(self, "entry_windows", tuple(normalized))

    def to_dict(self) -> dict[str, Any]:
        """Serialize the schedule for storage or reporting."""

        return {
            "event_date": self.event_date.isoformat(),
            "event_time_label": self.event_time_label,
            "entry_windows": [window.to_dict() for window in self.entry_windows],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> EventSchedule:
        """Build an EventSchedule from a mapping payload."""

        if "event_date" not in payload:
            raise KeyError("Missing required schedule field: 'event_date'")
        event_date_raw = payload["event_date"]
        if isinstance(event_date_raw, dt.datetime):
            event_date = event_date_raw.date()
        elif isinstance(event_date_raw, dt.date):
            event_date = event_date_raw
        elif isinstance(event_date_raw, str):
            event_date = dt.date.fromisoformat(event_date_raw)
        else:
            raise TypeError(
                f"Unsupported event_date value in schedule: {event_date_raw!r}"
            )

        windows_raw = payload.get("entry_windows", [])
        if not isinstance(windows_raw, list):
            raise TypeError("EventSchedule.entry_windows must be a list when provided.")
        windows = tuple(EventWindow.from_dict(item) for item in windows_raw)
        return cls(
            event_date=event_date,
            event_time_label=payload.get("event_time_label"),
            entry_windows=windows,
        )


@dataclass(frozen=True)
class EventSpec:
    """A first-class event definition usable across earnings and macro workflows."""

    family: EventFamily | str
    name: str
    underlying: str
    schedule: EventSchedule
    proxy_symbol: str | None = None
    notes: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "family", normalize_event_family(self.family))
        object.__setattr__(self, "name", normalize_event_name(self.name))

        underlying = self.underlying.strip().upper()
        if not underlying:
            raise ValueError("EventSpec.underlying must be non-empty.")
        object.__setattr__(self, "underlying", underlying)

        if not isinstance(self.schedule, EventSchedule):
            raise TypeError("EventSpec.schedule must be an EventSchedule instance.")

        if self.proxy_symbol is not None and not self.proxy_symbol.strip():
            raise ValueError("EventSpec.proxy_symbol cannot be blank.")
        if self.proxy_symbol is not None:
            object.__setattr__(self, "proxy_symbol", self.proxy_symbol.strip().upper())

        if self.notes is not None:
            notes = self.notes.strip()
            object.__setattr__(self, "notes", notes or None)

    @property
    def event_date(self) -> dt.date:
        """Compatibility accessor for legacy callers."""

        return self.schedule.event_date

    @property
    def event_time_label(self) -> str | None:
        """Compatibility accessor for legacy callers."""

        return self.schedule.event_time_label

    @property
    def entry_windows(self) -> tuple[EventWindow, ...]:
        """Timeline windows available for the event."""

        return self.schedule.entry_windows

    @property
    def key(self) -> str:
        """Stable event key for storage and reporting."""

        return (
            f"{self.family.value}:{self.name.lower()}:{self.underlying.upper()}:"
            f"{self.schedule.event_date.isoformat()}"
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize the event for reporting or storage."""

        return {
            "family": self.family.value,
            "name": self.name,
            "underlying": self.underlying,
            "schedule": self.schedule.to_dict(),
            # Compatibility keys for existing storage/report consumers.
            "event_date": self.schedule.event_date.isoformat(),
            "event_time_label": self.schedule.event_time_label,
            "entry_windows": [window.to_dict() for window in self.schedule.entry_windows],
            "proxy_symbol": self.proxy_symbol,
            "notes": self.notes,
            "event_key": self.key,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> EventSpec:
        """Deserialize an EventSpec from storage or reporting payloads."""

        required = ("family", "name", "underlying")
        missing = [field for field in required if field not in payload]
        if missing:
            raise KeyError(
                f"Missing required event fields: {', '.join(repr(field) for field in missing)}"
            )

        schedule_payload = payload.get("schedule")
        if schedule_payload is not None:
            if not isinstance(schedule_payload, Mapping):
                raise TypeError("EventSpec.schedule must be a mapping when provided.")
            schedule = EventSchedule.from_dict(schedule_payload)
        else:
            if "event_date" not in payload:
                raise KeyError(
                    "Missing required event field: 'event_date' (or provide 'schedule')."
                )
            entry_windows = payload.get("entry_windows", [])
            if entry_windows and not isinstance(entry_windows, list):
                raise TypeError("EventSpec.entry_windows must be a list when provided.")
            schedule = EventSchedule(
                event_date=payload["event_date"],
                event_time_label=payload.get("event_time_label"),
                entry_windows=tuple(EventWindow.from_dict(item) for item in entry_windows),
            )

        return cls(
            family=payload["family"],
            name=str(payload["name"]),
            underlying=str(payload["underlying"]),
            schedule=schedule,
            proxy_symbol=payload.get("proxy_symbol"),
            notes=payload.get("notes"),
        )
