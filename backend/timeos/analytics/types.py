"""Shared pure-Python types for the analytics layer (§14-§17).

Deliberately not SQLAlchemy models: the sessionizer, coverage reconstructor, classifier, and
focus/distraction engines are pure functions of `(events, config)` (§14, "the sessionizer is a
pure function... re-running must produce byte-identical output"). Keeping their input a plain
frozen dataclass makes that property testable without a database in every test.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True, slots=True)
class AnalyticsEvent:
    """One `raw_events` row, reduced to what analytics needs."""

    ts_utc: datetime
    type: str
    payload: dict[str, str] = field(default_factory=dict)

    @property
    def package(self) -> str | None:
        return self.payload.get("package")
