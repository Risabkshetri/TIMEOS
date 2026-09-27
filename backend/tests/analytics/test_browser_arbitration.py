"""§11.4's cross-browser arbitration — unit tests over synthetic overlapping interval sets from
three devices, plus the property test §33/§38 Phase 9 names explicitly: "browser time never
exceeds screen-on time"."""

from datetime import UTC, datetime, timedelta

from hypothesis import given
from hypothesis import strategies as st

from timeos.analytics.browser_arbitration import (
    ArbitrationInterval,
    arbitrate_browser_sessions,
    union_duration_seconds,
)

T0 = datetime(2026, 9, 14, 8, 0, 0, tzinfo=UTC)


def interval(family: str, start_s: float, end_s: float, domain: str = "github.com"):
    return ArbitrationInterval(
        browser_family=family,
        domain=domain,
        start_ts=T0 + timedelta(seconds=start_s),
        end_ts=T0 + timedelta(seconds=end_s),
    )


def test_non_overlapping_intervals_from_different_families_are_both_kept_unchanged():
    sessions = [interval("brave", 0, 60), interval("firefox", 120, 180)]
    result = arbitrate_browser_sessions(sessions)
    assert len(result) == 2
    assert result[0].end_ts == T0 + timedelta(seconds=60)
    assert result[1].start_ts == T0 + timedelta(seconds=120)


def test_overlapping_intervals_from_different_families_the_later_start_wins():
    # Brave holds focus 0-100s, but Firefox gains focus at 60s (overlap) — Firefox wins from 60s.
    sessions = [interval("brave", 0, 100), interval("firefox", 60, 150)]
    result = arbitrate_browser_sessions(sessions)
    by_family = {s.browser_family: s for s in result}
    assert by_family["brave"].end_ts == T0 + timedelta(seconds=60)
    assert by_family["brave"].truncated is True
    assert by_family["firefox"].start_ts == T0 + timedelta(seconds=60)
    assert by_family["firefox"].end_ts == T0 + timedelta(seconds=150)
    assert by_family["firefox"].truncated is False


def test_overlapping_intervals_from_the_same_family_are_not_arbitrated():
    # Two sessions from the SAME device/family overlapping would be a sessionizer bug, not
    # something arbitration should paper over — they pass through unchanged.
    sessions = [interval("brave", 0, 100), interval("brave", 50, 150)]
    result = arbitrate_browser_sessions(sessions)
    assert len(result) == 2
    assert {s.end_ts for s in result} == {T0 + timedelta(seconds=100), T0 + timedelta(seconds=150)}


def test_truncation_is_permanent_not_resumed_when_the_later_interval_ends():
    # "The later-starting interval wins FROM ITS START INSTANT" — Brave is cut short the moment
    # Firefox starts and does NOT get a second chunk after Firefox's own (shorter) interval ends;
    # a real focus-switch back to Brave would show up as its own later-starting interval in the
    # input, not an automatic revival of the truncated one.
    sessions = [interval("brave", 0, 200), interval("firefox", 10, 20)]
    result = arbitrate_browser_sessions(sessions)
    by_family = {s.browser_family: s for s in result}
    assert by_family["brave"].end_ts == T0 + timedelta(seconds=10)
    assert by_family["firefox"].start_ts == T0 + timedelta(seconds=10)
    assert by_family["firefox"].end_ts == T0 + timedelta(seconds=20)


def test_two_intervals_starting_at_the_exact_same_instant_the_earlier_processed_one_is_swallowed():
    # A genuine zero-duration case: with identical start times neither interval is truly "later",
    # so the tiebreak is the stable sort's input order — the first-listed one gets truncated to
    # nothing at the second's start and is dropped, rather than kept as a degenerate 0s row.
    sessions = [interval("brave", 0, 50), interval("firefox", 0, 100)]
    result = arbitrate_browser_sessions(sessions)
    assert len(result) == 1
    assert result[0].browser_family == "firefox"


def test_three_way_cascading_overlap_leaves_only_the_latest_starter_untruncated():
    sessions = [
        interval("brave", 0, 300),
        interval("chromium", 100, 300),
        interval("firefox", 200, 300),
    ]
    result = arbitrate_browser_sessions(sessions)
    by_family = {s.browser_family: s for s in result}
    assert by_family["brave"].end_ts == T0 + timedelta(seconds=100)
    assert by_family["chromium"].end_ts == T0 + timedelta(seconds=200)
    assert by_family["firefox"].end_ts == T0 + timedelta(seconds=300)
    assert by_family["firefox"].truncated is False


def test_empty_input_produces_empty_output():
    assert arbitrate_browser_sessions([]) == []


# --- union_duration_seconds -----------------------------------------------------


def test_union_of_non_overlapping_intervals_is_their_sum():
    intervals = [
        (T0, T0 + timedelta(seconds=60)),
        (T0 + timedelta(seconds=120), T0 + timedelta(seconds=180)),
    ]
    assert union_duration_seconds(intervals) == 120.0


def test_union_of_overlapping_intervals_counts_the_overlap_once():
    intervals = [
        (T0, T0 + timedelta(seconds=100)),
        (T0 + timedelta(seconds=50), T0 + timedelta(seconds=150)),
    ]
    assert union_duration_seconds(intervals) == 150.0  # not 200 (the naive sum)


def test_union_of_no_intervals_is_zero():
    assert union_duration_seconds([]) == 0.0


# --- property test: browser time never exceeds the observation window ---------

WINDOW_SECONDS = 3600  # a bounded synthetic window standing in for "screen-on time"
FAMILIES = ["brave", "chromium", "firefox"]


@st.composite
def _interval_strategy(draw):
    family = draw(st.sampled_from(FAMILIES))
    start_offset = draw(st.integers(min_value=0, max_value=WINDOW_SECONDS - 1))
    duration = draw(st.integers(min_value=1, max_value=WINDOW_SECONDS - start_offset))
    return interval(family, start_offset, start_offset + duration)


@given(st.lists(_interval_strategy(), min_size=0, max_size=30))
def test_arbitrated_union_never_exceeds_the_observation_window(sessions):
    arbitrated = arbitrate_browser_sessions(sessions)
    total = union_duration_seconds([(s.start_ts, s.end_ts) for s in arbitrated])
    assert total <= WINDOW_SECONDS
