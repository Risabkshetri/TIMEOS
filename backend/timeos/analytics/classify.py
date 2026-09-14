"""Layered app-session classifier — §15.2's "cheap -> expensive, first confident wins" stack.

A pure function of `(session, inputs)`: every layer's inputs (user rule, learned prior, seed
catalogue entry, neighbouring sessions) are passed in rather than fetched here, so this stays
testable without a database and reusable from both the pipeline and any future backfill tool.

L0 (explicit user rule) and L1 (learned prior, >=5 samples) read from `app_classifications` rows
the *caller* resolves — the correction loop that populates `source='user'`/`source='learned'`
rows doesn't exist until Phase 6/7, so in practice every classification today falls through to
L2/L3/L4. The layers are implemented now anyway: once Phase 6 lands, classifications immediately
start respecting user corrections with no change to this module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from importlib import resources

import yaml

from timeos.analytics.sessionize import AppSession

CONFIDENCE_FLOOR = 0.55
UNKNOWN = "unknown"

# The categories a §15.2 L3 "followed by work" modifier accepts as evidence of work resuming.
# Deliberately not all of §15.3's Work group (e.g. "admin" is chores, not the kind of engagement
# that retroactively reclassifies preceding media as Learning).
WORK_LIKE_CATEGORIES = frozenset(
    {"deep_work", "focused_work", "development", "research", "writing"}
)

# The categories a burst of entertainment-followed-by-work reclassifies *from*. Only categories
# that are plausibly "background learning material" (video/audio) qualify — reclassifying, say,
# a Social session as Learning just because you opened your IDE afterwards would be absurd.
RECLASSIFIABLE_AS_LEARNING = frozenset({"entertainment"})

FOLLOWED_BY_WORK_WINDOW = timedelta(minutes=15)
FOLLOWED_BY_WORK_MIN_DURATION = timedelta(minutes=30)
FOLLOWED_BY_WORK_CONFIDENCE = 0.68


@dataclass(frozen=True, slots=True)
class LearnedPrior:
    category_key: str
    confidence: float
    sample_count: int


@dataclass(frozen=True, slots=True)
class ClassificationResult:
    category_key: str
    confidence: float
    source: str  # user | learned | seed | context | unknown
    evidence: tuple[str, ...] = field(default_factory=tuple)


def load_seed_catalogue() -> dict[str, tuple[str, float]]:
    """Loads analytics/data/app_priors.yaml into {package: (category_key, confidence)}."""
    text = resources.files("timeos.analytics.data").joinpath("app_priors.yaml").read_text()
    raw = yaml.safe_load(text)
    return {
        pkg: (entry["category"], float(entry["confidence"])) for pkg, entry in (raw or {}).items()
    }


def classify_session(
    session: AppSession,
    *,
    user_rule: str | None = None,
    learned_prior: LearnedPrior | None = None,
    seed_catalogue: dict[str, tuple[str, float]] | None = None,
    following_sessions: list[AppSession] = (),  # sorted by start_ts, all after `session`
    category_by_app: dict[str, str] | None = None,  # app_key -> category_key, for context lookups
) -> ClassificationResult:
    if user_rule is not None:
        return ClassificationResult(user_rule, 1.0, "user", ("l0_user_rule",))

    if learned_prior is not None and learned_prior.sample_count >= 5:
        return ClassificationResult(
            learned_prior.category_key, learned_prior.confidence, "learned", ("l1_learned_prior",)
        )

    catalogue = seed_catalogue if seed_catalogue is not None else load_seed_catalogue()
    seed = catalogue.get(session.app_key)
    if seed is None:
        return ClassificationResult(UNKNOWN, 0.0, "unknown", ("l4_no_seed_entry",))

    category_key, confidence = seed
    evidence = ["l2_seed_catalogue"]

    if category_key in RECLASSIFIABLE_AS_LEARNING and category_by_app is not None:
        reclassified = _followed_by_work(session, following_sessions, category_by_app)
        if reclassified:
            category_key = "learning"
            confidence = FOLLOWED_BY_WORK_CONFIDENCE
            evidence.append("l3_followed_by_development")

    if confidence < CONFIDENCE_FLOOR:
        return ClassificationResult(
            UNKNOWN, confidence, "unknown", tuple(evidence + ["l4_below_floor"])
        )

    source = "context" if len(evidence) > 1 else "seed"
    return ClassificationResult(category_key, confidence, source, tuple(evidence))


def _followed_by_work(
    session: AppSession,
    following_sessions: list[AppSession],
    category_by_app: dict[str, str],
) -> bool:
    """§15.2: 'YouTube for 45 min followed within 15 min by >=30 min of Development -> Learning'."""
    deadline = session.end_ts + FOLLOWED_BY_WORK_WINDOW
    work_duration = timedelta()
    started_within_window = False

    for other in following_sessions:
        if other.start_ts >= deadline and not started_within_window:
            break
        category = category_by_app.get(other.app_key)
        if category not in WORK_LIKE_CATEGORIES:
            if not started_within_window:
                continue
            break  # a non-work session ends the contiguous work block we were accumulating
        if other.start_ts <= deadline:
            started_within_window = True
        work_duration += timedelta(seconds=other.duration_s)

    return started_within_window and work_duration >= FOLLOWED_BY_WORK_MIN_DURATION
