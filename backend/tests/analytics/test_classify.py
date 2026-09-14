"""§15.2 layered classifier — one test per layer, first-confident-wins order."""

from datetime import UTC, datetime, timedelta

from timeos.analytics.classify import (
    CONFIDENCE_FLOOR,
    LearnedPrior,
    classify_session,
    load_seed_catalogue,
)
from timeos.analytics.sessionize import AppSession

T0 = datetime(2026, 9, 14, 9, 0, 0, tzinfo=UTC)


def session(app_key: str, start_offset_s: float, duration_s: float) -> AppSession:
    start = T0 + timedelta(seconds=start_offset_s)
    return AppSession(
        app_key=app_key,
        start_ts=start,
        end_ts=start + timedelta(seconds=duration_s),
        interaction_count=1,
    )


SEED = {"com.example.youtube": ("entertainment", 0.62), "com.example.chrome": ("browsing", 0.60)}


def test_load_real_seed_catalogue_has_expected_shape():
    catalogue = load_seed_catalogue()
    category, confidence = catalogue["com.android.chrome"]
    assert category == "browsing"
    assert 0.55 <= confidence <= 0.80


def test_l0_user_rule_wins_terminally():
    s = session("com.example.youtube", 0, 60)
    result = classify_session(s, user_rule="learning", seed_catalogue=SEED)
    assert result.category_key == "learning"
    assert result.confidence == 1.0
    assert result.source == "user"


def test_l1_learned_prior_with_enough_samples_wins_over_seed():
    s = session("com.example.youtube", 0, 60)
    prior = LearnedPrior(category_key="learning", confidence=0.9, sample_count=5)
    result = classify_session(s, learned_prior=prior, seed_catalogue=SEED)
    assert result.category_key == "learning"
    assert result.source == "learned"


def test_l1_learned_prior_below_sample_threshold_falls_through_to_seed():
    s = session("com.example.youtube", 0, 60)
    prior = LearnedPrior(category_key="learning", confidence=0.9, sample_count=4)
    result = classify_session(s, learned_prior=prior, seed_catalogue=SEED)
    assert result.category_key == "entertainment"
    assert result.source == "seed"


def test_l2_seed_catalogue_used_when_no_higher_layer_applies():
    s = session("com.example.chrome", 0, 60)
    result = classify_session(s, seed_catalogue=SEED)
    assert result.category_key == "browsing"
    assert result.confidence == 0.60
    assert result.source == "seed"


def test_l4_unknown_package_has_no_seed_entry():
    s = session("com.example.mystery_app", 0, 60)
    result = classify_session(s, seed_catalogue=SEED)
    assert result.category_key == "unknown"
    assert result.confidence == 0.0
    assert result.source == "unknown"


def test_l4_confidence_below_floor_becomes_unknown():
    low_confidence_seed = {"com.example.iffy": ("browsing", CONFIDENCE_FLOOR - 0.01)}
    s = session("com.example.iffy", 0, 60)
    result = classify_session(s, seed_catalogue=low_confidence_seed)
    assert result.category_key == "unknown"
    assert result.source == "unknown"


def test_l3_entertainment_followed_by_development_reclassifies_to_learning():
    # §15.2: "YouTube for 45 min followed within 15 min by >=30 min of Development -> Learning".
    yt = session("com.example.youtube", 0, 45 * 60)
    dev = session("com.example.ide", yt.duration_s + 5 * 60, 35 * 60)  # 5 min after, in window
    result = classify_session(
        yt,
        seed_catalogue=SEED,
        following_sessions=[dev],
        category_by_app={"com.example.ide": "development"},
    )
    assert result.category_key == "learning"
    assert result.confidence == 0.68
    assert result.source == "context"
    assert "l3_followed_by_development" in result.evidence


def test_l3_entertainment_with_no_followup_stays_entertainment():
    # §15.2: "The same YouTube at 23:40 with no subsequent work -> Entertainment".
    yt = session("com.example.youtube", 0, 45 * 60)
    result = classify_session(yt, seed_catalogue=SEED, following_sessions=[], category_by_app={})
    assert result.category_key == "entertainment"
    assert result.source == "seed"


def test_l3_entertainment_followed_by_insufficient_work_duration_stays_entertainment():
    yt = session("com.example.youtube", 0, 45 * 60)
    # Only 10 minutes of development follow-up — below the 30-minute threshold.
    dev = session("com.example.ide", yt.duration_s + 5 * 60, 10 * 60)
    result = classify_session(
        yt,
        seed_catalogue=SEED,
        following_sessions=[dev],
        category_by_app={"com.example.ide": "development"},
    )
    assert result.category_key == "entertainment"


def test_l3_development_arriving_outside_the_15_minute_window_does_not_reclassify():
    yt = session("com.example.youtube", 0, 45 * 60)
    # Starts 20 minutes after YouTube ends — outside the 15-minute follow-up window.
    dev = session("com.example.ide", yt.duration_s + 20 * 60, 35 * 60)
    result = classify_session(
        yt,
        seed_catalogue=SEED,
        following_sessions=[dev],
        category_by_app={"com.example.ide": "development"},
    )
    assert result.category_key == "entertainment"
