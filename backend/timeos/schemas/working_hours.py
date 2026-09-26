"""§13/§18/§19: working_hours. Not in §12.2's endpoint table (that table only names Phase 6's
`/v1/goals` and `/v1/feedback/classification`), but §18's alignment engine and §19's Personal
Context Engine both depend on `working_hours` existing and being user-editable, so this fills that
gap the same way the codebase has filled other spec-silent gaps elsewhere: a minimal, clearly
documented surface. A user's weekly schedule is naturally edited as one unit (there are at most 7
rows, one per weekday), so PUT replaces the whole week rather than exposing per-weekday CRUD."""

from datetime import time

from pydantic import BaseModel, ConfigDict, Field, model_validator


class WorkingHoursEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    weekday: int = Field(ge=0, le=6)  # 0=Monday .. 6=Sunday, matching the model's own convention
    start_local: time
    end_local: time

    @model_validator(mode="after")
    def _start_before_end(self) -> "WorkingHoursEntry":
        if self.start_local >= self.end_local:
            raise ValueError("start_local must be before end_local")
        return self


class WorkingHoursReplaceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entries: list[WorkingHoursEntry]

    @model_validator(mode="after")
    def _unique_weekdays(self) -> "WorkingHoursReplaceRequest":
        weekdays = [e.weekday for e in self.entries]
        if len(weekdays) != len(set(weekdays)):
            raise ValueError("each weekday may appear at most once")
        return self
