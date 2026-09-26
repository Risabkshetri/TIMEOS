"""§20.2's second enforcement layer: "Allowlist + schema validation". `timeos.schemas.ai_context`
already gives every field a type and forbids extras via Pydantic — this module is the INDEPENDENT
backstop the spec calls for: it walks the plain serialized dict (not the Pydantic model) and checks
every key against a versioned, explicit set, so a bug in the schema itself (a stray field that
somehow validates, a future model that forgets `extra="forbid"`) still can't reach an LLM silently.
A new field must be added here deliberately — "a reviewable diff" (§20.2) — never inferred from
whatever `AIContext` currently contains.

Pure, no DB — importable from `timeos.ai`.
"""

from __future__ import annotations

ALLOWLIST_VERSION = "v1"

# Every key name that legitimately appears anywhere in timeos.schemas.ai_context.AIContext's
# serialized tree, including nested dict keys (e.g. Baselines.today_vs_mean's own keys). Checked
# by NAME only, not by full path — §20.3's ALLOWED list describes leaf concepts, not positions,
# and a name appearing safely in one place (e.g. "category") never becomes unsafe in another.
ALLOWED_LEAF_KEYS: frozenset[str] = frozenset(
    {
        "context_version",
        "scope",
        "date",
        "weekday",
        # DataQuality
        "data_quality",
        "coverage_ratio",
        "unknown_ratio",
        "devices_reporting",
        "unobserved_minutes",
        "offline_minutes",
        "caveats",
        # Totals
        "totals",
        "day_minutes",
        "observed_minutes",
        "screen_minutes",
        "active_minutes",
        # CategorySummary
        "categories",
        "category",
        "minutes",
        "share",
        "sessions",
        "avg_confidence",
        # FocusSummary
        "focus",
        "deep_sessions",
        "longest_minutes",
        "average_minutes",
        "total_focus_minutes",
        "avg_quality",
        "fragmentation_index",
        "context_switches",
        "switches_per_hour",
        "interruptions",
        # TimeOfDaySlot
        "time_of_day",
        "slot",
        "focus_minutes",
        "distraction_minutes",
        # TopAttentionEntry
        "top_attention",
        "rank",
        "bucket",
        # GoalSummary
        "goals",
        "name",
        "priority",
        "target_weekly_minutes",
        "aligned_minutes_today",
        "uncertainty",
        "week_attainment",
        # PatternSummary
        "patterns",
        "type",
        "occurrences",
        "strength",
        "status",
        # Baselines
        "baselines",
        "window_days",
        "valid_days",
        "screen_minutes_mean",
        "deep_work_minutes_mean",
        "fragmentation_mean",
        "today_vs_mean",
        # Baselines.today_vs_mean's own keys (see TODAY_VS_MEAN_KEYS in schemas/ai_context.py)
        "deep_work_minutes",
        "fragmentation",
    }
)


def find_disallowed_keys(node: object, path: str = "") -> dict[str, str]:
    """Walks a plain dict/list structure (from `AIContext.model_dump()`) and returns
    {dotted_path: key_name} for every dict key not in `ALLOWED_LEAF_KEYS`. Empty means clean."""
    violations: dict[str, str] = {}
    _walk(node, path, violations)
    return violations


def _walk(node: object, path: str, violations: dict[str, str]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            key_path = f"{path}.{key}" if path else str(key)
            if key not in ALLOWED_LEAF_KEYS:
                violations[key_path] = str(key)
            _walk(value, key_path, violations)
    elif isinstance(node, list):
        for index, item in enumerate(node):
            _walk(item, f"{path}[{index}]", violations)
