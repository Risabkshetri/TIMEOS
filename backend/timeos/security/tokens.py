"""Device token generation/verification and enrollment codes (§28).

Token shape: "{device_id}.{secret}". The device_id prefix is what makes verification fast:
Argon2id is deliberately slow, so a design that had to try every stored hash against a presented
secret would make ingest latency scale with device count. Instead the prefix gives an O(1) lookup
of the exact device row, and Argon2 verify runs exactly once per request — see api/deps.py.
"""

import secrets
import uuid

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

_hasher = PasswordHasher()

# No 0/O/1/I/L: avoids transcription errors when the user reads this off a screen.
_ENROLLMENT_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def generate_device_token(device_id: uuid.UUID) -> tuple[str, str]:
    """Returns (full_token_to_hand_to_the_client, raw_secret_to_hash_and_store)."""
    secret = secrets.token_urlsafe(32)
    return f"{device_id}.{secret}", secret


def hash_secret(secret: str) -> str:
    return _hasher.hash(secret)


def verify_secret(secret: str, stored_hash: str) -> bool:
    try:
        return _hasher.verify(stored_hash, secret)
    except VerifyMismatchError:
        return False
    except Exception:
        # Malformed/legacy hash, corrupted data, etc. — never let a verification error look like
        # a crash; it's simply "not authenticated".
        return False


def parse_token(token: str) -> tuple[uuid.UUID, str] | None:
    """Splits "{device_id}.{secret}" — returns None for any malformed token rather than raising,
    since this runs on every request with attacker-controlled input."""
    if "." not in token:
        return None
    device_id_str, secret = token.split(".", 1)
    try:
        device_id = uuid.UUID(device_id_str)
    except ValueError:
        return None
    if not secret:
        return None
    return device_id, secret


def generate_enrollment_code() -> str:
    return "".join(secrets.choice(_ENROLLMENT_ALPHABET) for _ in range(8))
