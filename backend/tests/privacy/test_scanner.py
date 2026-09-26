"""§20.2's content-scanning layer, §33's `test_url_email_token_scan` against a leak corpus."""

import pytest

from timeos.privacy.scanner import MAX_FREE_TEXT, scan_all_strings, scan_string

LEAK_CORPUS = [
    ("url_scheme", "check out https://example.com/path?token=abc"),
    ("bare_domain", "visit example.com for details"),
    ("email_shaped", "contact me at person@example.com"),
    ("long_digit_run", "call 5551234567 now"),
    ("path_separator", "/etc/passwd/secret"),
    ("windows_path_separator", "C:\\Users\\rishab\\secrets.txt"),
    # Deliberately NOT shaped like a real vendor's key prefix (e.g. "sk_live_") — a fabricated
    # fixture that happens to match a real secret format trips GitHub's push-protection secret
    # scanner even though it's fake, which is real friction for a test file, not a feature.
    ("high_entropy_token", "aB3xQ9zK2mN7pR4tW1vY8cU6oL0iH5jG2eF1dC0bA9zY8x"),
    ("too_long", "x" * (MAX_FREE_TEXT + 1)),
]

CLEAN_CORPUS = [
    "Development",
    "Deep Work",
    "Build the launch",
    "09:00-12:00",
    "2-3h",
    "confirmed",
    "POST_TASK_AVOIDANCE",
]


@pytest.mark.parametrize("label,value", LEAK_CORPUS)
def test_leaking_strings_are_flagged(label, value):
    assert scan_string(value) != [], f"expected a violation for {label!r}: {value!r}"


@pytest.mark.parametrize("value", CLEAN_CORPUS)
def test_clean_strings_are_not_flagged(value):
    assert scan_string(value) == []


def test_scan_all_strings_walks_nested_structures():
    payload = {
        "goals": [{"name": "Build https://leaky.example.com"}],
        "categories": [{"category": "Development"}],
    }
    findings = scan_all_strings(payload)
    assert "goals[0].name" in findings
    assert "url" in findings["goals[0].name"]
    assert "categories[0].category" not in findings


def test_scan_all_strings_returns_empty_for_a_clean_payload():
    payload = {"categories": [{"category": "Development", "minutes": 186}]}
    assert scan_all_strings(payload) == {}


def test_multiple_violation_classes_can_fire_on_one_string():
    # A URL is inherently also path-separator-shaped.
    violations = scan_string("https://example.com/a/b")
    assert "url" in violations
    assert "path_separator" in violations
