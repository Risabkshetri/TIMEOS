"""§14.3/§38 Phase 10's cross-device coverage merge — unit tests plus the property test §33 names
explicitly: "unified observed time never exceeds day duration"."""

import uuid
from datetime import UTC, datetime, timedelta

from hypothesis import given
from hypothesis import strategies as st

from timeos.analytics.coverage import DEVICE_OFFLINE, IDLE, TRACKED, UNOBSERVED, CoverageInterval
from timeos.analytics.merge import (
    DeviceActivity,
    cluster_cross_device_activities,
    merge_device_coverage,
)

T0 = datetime(2026, 9, 14, 8, 0, 0, tzinfo=UTC)
PHONE = uuid.uuid4()
BROWSER = uuid.uuid4()


def interval(state: str, start_s: float, end_s: float) -> CoverageInterval:
    return CoverageInterval(T0 + timedelta(seconds=start_s), T0 + timedelta(seconds=end_s), state)


def test_a_single_device_is_just_its_own_observed_time():
    result = merge_device_coverage({"phone": [interval(TRACKED, 0, 100), interval(IDLE, 100, 150)]})
    assert result.observed_s == 150.0
    assert result.dual_device_s == 0.0


def test_non_overlapping_devices_sum_with_no_dual_device_time():
    result = merge_device_coverage(
        {
            "phone": [interval(TRACKED, 0, 100)],
            "browser": [interval(TRACKED, 200, 300)],
        }
    )
    assert result.observed_s == 200.0
    assert result.dual_device_s == 0.0


def test_overlapping_devices_are_unioned_not_summed():
    result = merge_device_coverage(
        {
            "phone": [interval(TRACKED, 0, 100)],
            "browser": [interval(TRACKED, 50, 150)],
        }
    )
    # Union of [0,100) and [50,150) is [0,150) = 150s, not 100+100=200s.
    assert result.observed_s == 150.0
    assert result.dual_device_s == 50.0  # the [50,100) overlap


def test_fully_contained_overlap():
    result = merge_device_coverage(
        {
            "phone": [interval(TRACKED, 0, 200)],
            "browser": [interval(TRACKED, 50, 100)],
        }
    )
    assert result.observed_s == 200.0
    assert result.dual_device_s == 50.0


def test_three_devices_simultaneously_observed_still_counts_as_dual_device():
    # dual_device_s means ">=2 devices", not "exactly 2" — a triple-overlap is still dual_device.
    result = merge_device_coverage(
        {
            "phone": [interval(TRACKED, 0, 100)],
            "browser_a": [interval(TRACKED, 0, 100)],
            "browser_b": [interval(TRACKED, 0, 100)],
        }
    )
    assert result.observed_s == 100.0
    assert result.dual_device_s == 100.0


def test_idle_counts_as_observed_for_union_purposes():
    result = merge_device_coverage({"phone": [interval(IDLE, 0, 60)]})
    assert result.observed_s == 60.0


def test_unobserved_and_offline_states_are_excluded():
    result = merge_device_coverage(
        {"phone": [interval(UNOBSERVED, 0, 60), interval(DEVICE_OFFLINE, 60, 120)]}
    )
    assert result.observed_s == 0.0


def test_no_devices_produces_zero():
    assert merge_device_coverage({}) == merge_device_coverage({"phone": []})


def test_adjacent_non_overlapping_intervals_touch_without_being_double_counted():
    result = merge_device_coverage(
        {
            "phone": [interval(TRACKED, 0, 100)],
            "browser": [interval(TRACKED, 100, 200)],
        }
    )
    assert result.observed_s == 200.0
    assert result.dual_device_s == 0.0


# --- property test: unified observed time never exceeds the window ------------

WINDOW_SECONDS = 3600
DEVICE_NAMES = ["phone", "browser_brave", "browser_firefox"]


@st.composite
def _device_intervals(draw):
    device = draw(st.sampled_from(DEVICE_NAMES))
    state = draw(st.sampled_from([TRACKED, IDLE, UNOBSERVED, DEVICE_OFFLINE]))
    start = draw(st.integers(min_value=0, max_value=WINDOW_SECONDS - 1))
    duration = draw(st.integers(min_value=1, max_value=WINDOW_SECONDS - start))
    return device, interval(state, start, start + duration)


@given(st.lists(_device_intervals(), min_size=0, max_size=40))
def test_unified_observed_time_never_exceeds_the_window(entries):
    intervals_by_device: dict[str, list[CoverageInterval]] = {}
    for device, iv in entries:
        intervals_by_device.setdefault(device, []).append(iv)

    result = merge_device_coverage(intervals_by_device)
    assert result.observed_s <= WINDOW_SECONDS
    assert result.dual_device_s <= result.observed_s


# --- cluster_cross_device_activities --------------------------------------------


def activity(device_id, category, start_s, end_s, confidence=0.7):
    return DeviceActivity(
        device_id=device_id,
        category_key=category,
        start_ts=T0 + timedelta(seconds=start_s),
        end_ts=T0 + timedelta(seconds=end_s),
        duration_s=end_s - start_s,
        confidence=confidence,
        source_session_ids=(uuid.uuid4(),),
    )


def test_a_single_activity_passes_through_unclustered():
    result = cluster_cross_device_activities([activity(PHONE, "development", 0, 100)])
    assert len(result) == 1
    assert result[0].is_cross_device is False
    assert result[0].device_ids == (PHONE,)


def test_overlapping_same_category_different_devices_cluster():
    activities = [
        activity(PHONE, "development", 0, 100),
        activity(BROWSER, "development", 50, 150),
    ]
    result = cluster_cross_device_activities(activities)
    assert len(result) == 1
    cluster = result[0]
    assert cluster.is_cross_device is True
    assert set(cluster.device_ids) == {PHONE, BROWSER}
    assert cluster.start_ts == T0
    assert cluster.end_ts == T0 + timedelta(seconds=150)
    assert cluster.duration_s == 150.0  # union, not 100+100


def test_same_device_activities_never_cluster_with_each_other():
    activities = [
        activity(PHONE, "development", 0, 100),
        activity(PHONE, "development", 50, 150),
    ]
    result = cluster_cross_device_activities(activities)
    assert len(result) == 2
    assert all(not a.is_cross_device for a in result)


def test_different_categories_do_not_cluster_even_if_overlapping():
    activities = [
        activity(PHONE, "development", 0, 100),
        activity(BROWSER, "entertainment", 50, 150),
    ]
    result = cluster_cross_device_activities(activities)
    assert len(result) == 2


def test_activities_within_the_gap_but_not_overlapping_still_cluster():
    activities = [
        activity(PHONE, "development", 0, 100),
        activity(BROWSER, "development", 200, 300),  # 100s gap, under the 5-minute default
    ]
    result = cluster_cross_device_activities(activities)
    assert len(result) == 1
    assert result[0].is_cross_device is True


def test_activities_far_apart_do_not_cluster():
    activities = [
        activity(PHONE, "development", 0, 100),
        activity(BROWSER, "development", 10_000, 10_100),
    ]
    result = cluster_cross_device_activities(activities)
    assert len(result) == 2


def test_clustered_confidence_is_duration_weighted():
    activities = [
        activity(PHONE, "development", 0, 300, confidence=0.9),  # 300s @ 0.9
        activity(BROWSER, "development", 0, 100, confidence=0.6),  # 100s @ 0.6
    ]
    result = cluster_cross_device_activities(activities)
    expected = (300 * 0.9 + 100 * 0.6) / 400
    assert result[0].confidence == expected


def test_empty_input_produces_empty_output():
    assert cluster_cross_device_activities([]) == []
