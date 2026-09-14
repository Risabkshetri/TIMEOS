"""Session token signing/verification — pure, no DB (§25, §28)."""

import uuid
from datetime import UTC, datetime, timedelta

from timeos.security.sessions import (
    SESSION_MAX_AGE,
    create_session_token,
    verify_session_token,
)

SECRET = "test-secret-key"
USER_ID = uuid.uuid4()
NOW = datetime(2026, 9, 14, 12, 0, 0, tzinfo=UTC)


def test_a_freshly_issued_token_verifies():
    token = create_session_token(USER_ID, SECRET, NOW)
    assert verify_session_token(token, SECRET, NOW, password_changed_at=None) == USER_ID


def test_a_tampered_signature_is_rejected():
    token = create_session_token(USER_ID, SECRET, NOW)
    user_id_part, ts_part, sig_part = token.split(".")
    tampered = f"{user_id_part}.{ts_part}.{'0' * len(sig_part)}"
    assert verify_session_token(tampered, SECRET, NOW, password_changed_at=None) is None


def test_a_tampered_user_id_is_rejected_even_with_a_valid_looking_signature():
    token = create_session_token(USER_ID, SECRET, NOW)
    _user_id_part, ts_part, sig_part = token.split(".")
    forged = f"{uuid.uuid4()}.{ts_part}.{sig_part}"
    assert verify_session_token(forged, SECRET, NOW, password_changed_at=None) is None


def test_wrong_secret_key_is_rejected():
    token = create_session_token(USER_ID, SECRET, NOW)
    assert verify_session_token(token, "a-different-secret", NOW, password_changed_at=None) is None


def test_malformed_token_is_rejected_not_raised():
    assert verify_session_token("not-a-real-token", SECRET, NOW, password_changed_at=None) is None
    assert verify_session_token("a.b", SECRET, NOW, password_changed_at=None) is None
    assert verify_session_token("", SECRET, NOW, password_changed_at=None) is None


def test_token_older_than_thirty_days_is_rejected():
    issued_at = NOW - SESSION_MAX_AGE - timedelta(seconds=1)
    token = create_session_token(USER_ID, SECRET, issued_at)
    assert verify_session_token(token, SECRET, NOW, password_changed_at=None) is None


def test_token_within_thirty_days_still_verifies():
    issued_at = NOW - SESSION_MAX_AGE + timedelta(hours=1)
    token = create_session_token(USER_ID, SECRET, issued_at)
    assert verify_session_token(token, SECRET, NOW, password_changed_at=None) == USER_ID


def test_a_far_future_dated_token_is_rejected():
    token = create_session_token(USER_ID, SECRET, NOW + timedelta(days=1))
    assert verify_session_token(token, SECRET, NOW, password_changed_at=None) is None


def test_token_issued_before_a_password_change_is_rejected():
    token = create_session_token(USER_ID, SECRET, NOW - timedelta(minutes=10))
    password_changed_at = NOW - timedelta(minutes=5)
    assert verify_session_token(token, SECRET, NOW, password_changed_at) is None


def test_token_issued_after_a_password_change_still_verifies():
    password_changed_at = NOW - timedelta(minutes=10)
    token = create_session_token(USER_ID, SECRET, NOW - timedelta(minutes=5))
    assert verify_session_token(token, SECRET, NOW, password_changed_at) == USER_ID


def test_token_issued_milliseconds_after_a_password_change_in_the_same_second_still_verifies():
    # Regression: truncating the signed timestamp to whole seconds let a token issued a few
    # hundred ms after password_changed_at round DOWN to a value that reads as issued before it
    # — exactly what happens when an account is created and logged into within the same test
    # (or the same real second in production).
    password_changed_at = datetime(2026, 9, 14, 12, 0, 0, 950000, tzinfo=UTC)
    issued_at = datetime(2026, 9, 14, 12, 0, 0, 980000, tzinfo=UTC)  # 30ms later, same second
    token = create_session_token(USER_ID, SECRET, issued_at)
    assert verify_session_token(token, SECRET, issued_at, password_changed_at) == USER_ID
