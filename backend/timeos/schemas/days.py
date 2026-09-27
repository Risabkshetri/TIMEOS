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
    dual_device_s: float

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


class ActivityOut(BaseModel):
    id: str
    category_key: str
    category_label: str
    app_keys: list[str]
    devices: list[str]
    is_cross_device: bool
    start_ts: datetime
    end_ts: datetime
    duration_s: float
    confidence: float
    classification_source: str


class TimelineResponse(BaseModel):
    """§38 Phase 10: `view=per_device` (the default, and this endpoint's original Phase 4/9 shape)
    populates `devices` — one band per device, including browser devices now shown for the first
    time (their `BrowserSession` rows adapted into the same `coverage`/`sessions` shape, domain as
    `app_key`, coverage always TRACKED since a browser has no OS-level idle/offline signal).
    `view=unified` instead populates `unified` — the already cross-device-clustered `activities`
    rows (see `timeos.analytics.merge.cluster_cross_device_activities`), so a genuinely
    simultaneous phone+laptop stretch of work renders as ONE band, not two overlapping ones."""

    local_date: date
    view: str
    devices: list[DeviceTimelineOut] = []
    unified: list[ActivityOut] = []


class FocusSessionOut(BaseModel):
    category_key: str
    category_label: str
    start_ts: datetime
    end_ts: datetime
    duration_s: float
    interruption_count: int
    tool_switch_count: int
    attributed_ratio: float
    is_deep_work: bool


class FocusResponse(BaseModel):
    local_date: date
    sessions: list[FocusSessionOut]


class ActivitiesResponse(BaseModel):
    local_date: date
    activities: list[ActivityOut]
