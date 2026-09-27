"""Layered app-session classifier — §15.2's "cheap -> expensive, first confident wins" stack.

A pure function of `(session, inputs)`: every layer's inputs (user rule, learned prior, seed
catalogue entry, neighbouring sessions) are passed in rather than fetched here, so this stays
testable without a database and reusable from both the pipeline and any future backfill tool.

L0 (explicit user rule) and L1 (learned prior, >=5 samples) read from `app_classifications` rows
the *caller* resolves. Phase 6's correction loop (timeos.api.feedback) is what actually populates
`source='user'`/`source='learned'` rows now, via `bayesian_update_app_classification` below.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
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


def load_domain_seed_catalogue() -> dict[str, tuple[str, float]]:
    """§38 Phase 10: the L2 seed catalogue for browser telemetry. `classify_session` itself needs
    no changes to classify a domain instead of an Android package — a `BrowserSession` is adapted
    into an `AppSession`-shaped object with the domain as `app_key` before being classified (see
    `timeos.jobs.pipeline`), and this catalogue is passed in wherever `load_seed_catalogue()`'s
    app catalogue normally would be."""
    text = resources.files("timeos.analytics.data").joinpath("domain_priors.yaml").read_text()
    raw = yaml.safe_load(text)
    return {
        domain: (entry["category"], float(entry["confidence"]))
        for domain, entry in (raw or {}).items()
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


# §15.4's correction loop: "updates app_classifications (Bayesian update with a recency half-life
# of 60 days)". The spec names the mechanism but not an exact formula (unlike, say, §16's focus
# quality score) — this is this module's documented interpretation, kept in the same 0.75-0.95
# confidence band L1 is defined to occupy (§15.2) and gated at the same >=5-sample threshold
# classify_session already checks for L1 to take effect.
RECENCY_HALF_LIFE_DAYS = 60.0
LEARNED_CONFIDENCE_FLOOR = 0.75
LEARNED_CONFIDENCE_CEILING = 0.95
LEARNED_CONFIDENCE_STEP = 0.04  # reaches the ceiling at ~5 samples: 0.75 + 0.04*(5-1) = 0.91


@dataclass(frozen=True, slots=True)
class LearnedClassificationUpdate:
    category_key: str
    confidence: float
    sample_count: int


def bayesian_update_app_classification(
    corrected_category_key: str,
    existing: LearnedPrior | None,
    existing_updated_at: datetime | None,
    now: datetime | None = None,
) -> LearnedClassificationUpdate:
    """One correction's effect on an app's learned prior.

    A correction that CONTRADICTS the existing learned category doesn't try to blend two
    different categories' evidence into one number — it starts a fresh accumulation for the
    corrected category. This is a direct correction, the strongest signal this system ever
    receives about an app; treating it as one vote among a stale, differently-labelled history
    would make the very case it's meant to fix (a wrong classification) the hardest one to
    correct. Old evidence's effect on ALREADY-COMPUTED days is untouched either way — only
    Phase 6's opt-in retroactive recompute changes history, never a classification update alone.
    """
    now = now or datetime.now(UTC)

    if existing is None or existing.category_key != corrected_category_key:
        return LearnedClassificationUpdate(corrected_category_key, LEARNED_CONFIDENCE_FLOOR, 1)

    if existing_updated_at is None:
        decayed_samples = 0.0
    else:
        days_elapsed = max((now - existing_updated_at).total_seconds() / 86400, 0.0)
        decay = 0.5 ** (days_elapsed / RECENCY_HALF_LIFE_DAYS)
        decayed_samples = existing.sample_count * decay

    new_sample_count = decayed_samples + 1
    confidence = min(
        LEARNED_CONFIDENCE_CEILING,
        LEARNED_CONFIDENCE_FLOOR + LEARNED_CONFIDENCE_STEP * (new_sample_count - 1),
    )
    # Rounds up: a decayed 4.2 "effective" samples plus this new one should read as 5 real
    # corrections towards classify_session's own >=5 L1 threshold, not be floored back to 4.
    return LearnedClassificationUpdate(
        corrected_category_key, confidence, max(1, round(new_sample_count))
    )
