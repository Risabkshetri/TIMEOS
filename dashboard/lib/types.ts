// Mirrors backend/timeos/schemas/days.py and health.py. Kept as plain interfaces (no runtime
// validation library) since this is a trusted first-party API on the same deployment — the
// backend's own Pydantic schemas are the actual contract enforcement point.

export interface DailyMetrics {
  local_date: string;
  day_start_utc: string;
  day_end_utc: string;
  duration_seconds: number;

  observed_s: number;
  tracked_s: number;
  idle_s: number;
  unobserved_s: number;
  offline_s: number;
  coverage_ratio: number;

  screen_time_s: number;
  active_time_s: number;

  deep_work_s: number;
  focused_work_s: number;
  shallow_work_s: number;
  communication_s: number;
  learning_s: number;
  entertainment_s: number;
  social_s: number;
  distraction_s: number;
  unknown_s: number;
  unknown_ratio: number;

  context_switches: number;
  switches_per_hour: number;
  interruptions: number;
  fragmentation_index: number | null;

  longest_focus_s: number;
  avg_focus_s: number;
  focus_session_count: number;

  unlock_count: number;
  tz_transition: boolean;
  revised: boolean;
  computed_at: string;
  pipeline_version: string;
}

export interface CategoryBreakdown {
  key: string;
  label: string;
  duration_s: number;
}

export interface DayResponse {
  metrics: DailyMetrics;
  categories: CategoryBreakdown[];
}

// TRACKED | IDLE | UNOBSERVED | DEVICE_OFFLINE — see backend/timeos/analytics/coverage.py.
export type CoverageState = "TRACKED" | "IDLE" | "UNOBSERVED" | "DEVICE_OFFLINE";

export interface CoverageInterval {
  start_ts: string;
  end_ts: string;
  state: CoverageState;
}

export interface AppSessionOut {
  app_key: string;
  start_ts: string;
  end_ts: string;
  duration_s: number;
  interaction_count: number;
}

export interface DeviceTimeline {
  device_id: string;
  name: string;
  coverage: CoverageInterval[];
  sessions: AppSessionOut[];
}

export interface TimelineResponse {
  local_date: string;
  devices: DeviceTimeline[];
}

export interface FocusSessionOut {
  category_key: string;
  category_label: string;
  start_ts: string;
  end_ts: string;
  duration_s: number;
  interruption_count: number;
  tool_switch_count: number;
  attributed_ratio: number;
  is_deep_work: boolean;
}

export interface FocusResponse {
  local_date: string;
  sessions: FocusSessionOut[];
}

export interface CollectorHealth {
  device_id: string;
  name: string;
  platform: string;
  last_seen_at: string | null;
  last_seq: number;
  revoked: boolean;
  rejected_batch_count: number;
}

export interface CollectorsHealthResponse {
  collectors: CollectorHealth[];
}

export interface ActivityOut {
  id: string;
  category_key: string;
  category_label: string;
  app_keys: string[];
  start_ts: string;
  end_ts: string;
  duration_s: number;
  confidence: number;
  classification_source: string;
}

export interface ActivitiesResponse {
  local_date: string;
  activities: ActivityOut[];
}

// Mirrors backend/timeos/schemas/categories.py.
export interface CategoryOut {
  id: string;
  key: string;
  label: string;
  parent_id: string | null;
  is_system: boolean;
}

// Mirrors backend/timeos/schemas/goals.py.
export interface GoalMappingOut {
  id: string;
  category_id: string | null;
  app_key: string | null;
  weight: number;
}

export interface GoalOut {
  id: string;
  name: string;
  priority: number;
  target_minutes_per_week: number;
  target_behavior: string | null;
  active_from: string;
  active_to: string | null;
  archived: boolean;
  mappings: GoalMappingOut[];
}

export interface ClassificationCorrectionResponse {
  new_activity_id: string;
  app_classification_source: string;
  app_classification_confidence: number;
  app_classification_sample_count: number;
  retroactively_recomputed_dates: string[];
}

export interface GoalAlignmentOut {
  label: string; // always "INFERENCE" — §18's mandatory honesty labelling
  goal_id: string;
  window_days: number;
  target_minutes: number;
  aligned_minutes: number;
  range_low_minutes: number;
  range_high_minutes: number;
  attainment_ratio: number;
  coverage_ratio: number;
}

// Mirrors backend/timeos/schemas/privacy.py.
export interface PrivacyAuditEventOut {
  id: string;
  occurred_at: string;
  actor: string;
  allowlist_version: string;
  ai_share_app_names: boolean;
  field_count: number;
  outcome: string;
  rejected_fields: string[];
  payload_sha256: string;
}

export interface PrivacyPreviewResponse {
  date: string;
  context: Record<string, unknown>;
  payload_sha256: string;
}

// Mirrors backend/timeos/schemas/insights.py.
export interface InsightOut {
  id: string;
  kind: string; // wins | problems | patterns | distractions | goal_alignment | recommendation
  claim: string;
  evidence: {
    fields?: string[];
    values?: Record<string, unknown>;
    narrative?: string;
    rationale?: string;
    expected_effect?: string;
    effort?: string;
    measurable_check?: string;
  };
  confidence: number;
  evidence_verified: boolean;
  epistemic_status: string | null; // FACT | INFERENCE | HYPOTHESIS | null (recommendations)
}

export interface AnalysisOut {
  id: string;
  scope: string;
  scope_key: string;
  provider: string;
  model: string;
  day_score: number | null;
  score_rationale: string | null;
  summary: string | null;
  overall_confidence: number | null;
  data_caveats: string[];
  tomorrow_priorities: string[];
  validation_status: string; // ok | partial | failed
  created_at: string;
  insights: InsightOut[];
}
