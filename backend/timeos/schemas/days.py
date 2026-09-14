"""§25 dashboard read schemas: /v1/days/{date} and /v1/days/{date}/timeline."""

from datetime import date, datetime

from pydantic import BaseModel


class CategoryBreakdown(BaseModel):
    key: str
    label: str
    duration_s: float


class DailyMetricsOut(BaseModel):
    local_date: date
    day_start_utc: datetime
    day_end_utc: datetime
    duration_seconds: float

    observed_s: float
    tracked_s: float
    idle_s: float
    unobserved_s: float
    offline_s: float
    coverage_ratio: float

    screen_time_s: float
    active_time_s: float

    deep_work_s: float
    focused_work_s: float
    shallow_work_s: float
    communication_s: float
    learning_s: float
    entertainment_s: float
    social_s: float
    distraction_s: float
    unknown_s: float
    unknown_ratio: float

    context_switches: int
    switches_per_hour: float
    interruptions: int
    fragmentation_index: float | None

    longest_focus_s: float
    avg_focus_s: float
    focus_session_count: int

    unlock_count: int
    tz_transition: bool
    revised: bool
    computed_at: datetime
    pipeline_version: str


class DayResponse(BaseModel):
    metrics: DailyMetricsOut
    categories: list[CategoryBreakdown]


class CoverageIntervalOut(BaseModel):
    start_ts: datetime
    end_ts: datetime
    state: str


class AppSessionOut(BaseModel):
    app_key: str
    start_ts: datetime
    end_ts: datetime
    duration_s: float
    interaction_count: int


class DeviceTimelineOut(BaseModel):
    device_id: str
    name: str
    coverage: list[CoverageIntervalOut]
    sessions: list[AppSessionOut]


class TimelineResponse(BaseModel):
    local_date: date
    devices: list[DeviceTimelineOut]
