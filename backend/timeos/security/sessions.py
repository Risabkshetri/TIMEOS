"""Dashboard session tokens (§25, §28): httpOnly, Secure, SameSite=Strict cookie, 30-day sliding
expiry, no server-side session store.

A signed cookie rather than a `sessions` table: the compact §13 schema in the spec's Phase 5
entry lists only `user_feedback` as a database change, so a session store table would be scope
creep beyond what's specified. Revocation (rotating the dashboard password invalidates every
outstanding session, per §28's "revoke the device first, then rotate the dashboard password"
runbook) is achieved via `users.password_changed_at`: a token's signed issued-at time is checked
against it on every request, so a password change invalidates all prior tokens without needing
anything to be deleted.

Pure functions of (secret_key, now, password_changed_at) — no DB access here — so the signing and
verification logic is fully unit-testable; api/auth.py wires this to the actual cookie and to a
User row.
"""

import hashlib
import hmac
import uuid
from datetime import UTC, datetime, timedelta

SESSION_MAX_AGE = timedelta(days=30)
# Tolerates modest clock skew between the process that signed a token and the one verifying it
# (e.g. a container restarted with a slightly different clock) without accepting arbitrarily
# future-dated tokens, which would otherwise never expire.
CLOCK_SKEW_TOLERANCE = timedelta(minutes=5)


def create_session_token(user_id: uuid.UUID, secret_key: str, issued_at: datetime) -> str:
    # Microseconds, not whole seconds: truncating sub-second precision here made a token issued
    # a few hundred ms after password_changed_at able to round down to a timestamp that reads as
    # BEFORE it, spuriously rejecting a freshly-issued, legitimately-later session.
    timestamp = str(int(issued_at.timestamp() * 1_000_000))
    payload = f"{user_id}.{timestamp}"
    signature = hmac.new(secret_key.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{signature}"


def verify_session_token(
    token: str,
    secret_key: str,
    now: datetime,
    password_changed_at: datetime | None,
) -> uuid.UUID | None:
    """Returns the authenticated user_id, or None for any invalid/expired/tampered/stale token."""
    parts = token.split(".")
    if len(parts) != 3:
        return None
    user_id_str, timestamp_str, signature = parts

    payload = f"{user_id_str}.{timestamp_str}"
    expected_signature = hmac.new(secret_key.encode(), payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected_signature):
        return None

    try:
        user_id = uuid.UUID(user_id_str)
        issued_at = datetime.fromtimestamp(int(timestamp_str) / 1_000_000, tz=UTC)
    except (ValueError, OverflowError, OSError):
        return None

    if issued_at > now + CLOCK_SKEW_TOLERANCE:
        return None
    if now - issued_at > SESSION_MAX_AGE:
        return None
    if password_changed_at is not None and issued_at < password_changed_at:
        return None

    return user_id
