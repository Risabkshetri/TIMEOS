"""§15.4's correction loop: Bayesian update of app_classifications with a 60-day recency
half-life."""

from datetime import UTC, datetime, timedelta

import pytest

from timeos.analytics.classify import (
    LEARNED_CONFIDENCE_CEILING,
    LEARNED_CONFIDENCE_FLOOR,
    LearnedPrior,
    bayesian_update_app_classification,
)

NOW = datetime(2026, 9, 20, 12, 0, 0, tzinfo=UTC)


def test_first_ever_correction_starts_at_the_confidence_floor_with_one_sample():
    result = bayesian_update_app_classification("development", None, None, now=NOW)
    assert result.category_key == "development"
    assert result.confidence == LEARNED_CONFIDENCE_FLOOR
    assert result.sample_count == 1


def test_repeated_agreeing_corrections_converge_after_five_samples():
    # §38 Phase 6's test list: "learned prior converges after 5 samples".
    prior = None
    updated_at = None
    for _ in range(5):
        update = bayesian_update_app_classification("development", prior, updated_at, now=NOW)
        prior = LearnedPrior(update.category_key, update.confidence, update.sample_count)
        updated_at = NOW  # each correction happens "now" — no decay between them

    assert prior.sample_count == 5
    assert prior.confidence >= 0.9
    assert prior.confidence <= LEARNED_CONFIDENCE_CEILING


def test_confidence_never_exceeds_the_ceiling_however_many_samples():
    prior = LearnedPrior("development", LEARNED_CONFIDENCE_CEILING, 100)
    result = bayesian_update_app_classification("development", prior, NOW, now=NOW)
    assert result.confidence <= LEARNED_CONFIDENCE_CEILING


def test_a_contradicting_correction_resets_to_the_new_category_not_a_blend():
    prior = LearnedPrior("entertainment", 0.9, 5)
    result = bayesian_update_app_classification("learning", prior, NOW, now=NOW)
    assert result.category_key == "learning"
    assert result.confidence == LEARNED_CONFIDENCE_FLOOR
    assert result.sample_count == 1


def test_old_evidence_decays_toward_zero_after_many_half_lives():
    old_update = NOW - timedelta(days=180)  # 3 half-lives: 0.5**3 = 0.125
    prior = LearnedPrior("development", 0.9, 8)
    result = bayesian_update_app_classification("development", prior, old_update, now=NOW)
    # decayed_samples = 8 * 0.125 = 1.0, plus this new one = 2.0
    assert result.sample_count == 2


def test_recent_evidence_barely_decays():
    recent_update = NOW - timedelta(hours=1)
    prior = LearnedPrior("development", 0.9, 5)
    result = bayesian_update_app_classification("development", prior, recent_update, now=NOW)
    assert result.sample_count == 6  # ~5 * (nearly 1.0) + 1, rounds to 6


def test_missing_updated_at_is_treated_as_no_prior_evidence():
    prior = LearnedPrior("development", 0.9, 5)
    result = bayesian_update_app_classification("development", prior, None, now=NOW)
    assert result.sample_count == 1


@pytest.mark.parametrize("sample_count", [1, 2, 3])
def test_confidence_always_stays_within_the_l1_band(sample_count):
    prior = LearnedPrior("development", 0.8, sample_count)
    result = bayesian_update_app_classification("development", prior, NOW, now=NOW)
    assert LEARNED_CONFIDENCE_FLOOR <= result.confidence <= LEARNED_CONFIDENCE_CEILING
