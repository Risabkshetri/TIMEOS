"""Pure unit tests for timeos.security.tokens — no database needed."""

import uuid

from timeos.security.tokens import (
    generate_device_token,
    generate_enrollment_code,
    hash_secret,
    parse_token,
    verify_secret,
)


def test_generate_device_token_round_trips_through_parse():
    device_id = uuid.uuid4()
    token, secret = generate_device_token(device_id)
    parsed = parse_token(token)
    assert parsed == (device_id, secret)


def test_hash_and_verify_secret():
    secret = "a-real-secret-value"
    hashed = hash_secret(secret)
    assert verify_secret(secret, hashed) is True
    assert verify_secret("wrong-secret", hashed) is False


def test_parse_token_rejects_malformed_input():
    assert parse_token("no-dot-separator") is None
    assert parse_token("not-a-uuid.somesecret") is None
    assert parse_token(f"{uuid.uuid4()}.") is None  # empty secret


def test_verify_secret_never_raises_on_garbage_hash():
    assert verify_secret("anything", "not-a-real-argon2-hash") is False


def test_enrollment_code_shape():
    code = generate_enrollment_code()
    assert len(code) == 8
    assert code.isupper() or code.isdigit() or code.isalnum()
    # excludes visually ambiguous characters
    for ambiguous in "0O1IL":
        assert ambiguous not in code


def test_enrollment_codes_are_not_all_identical():
    codes = {generate_enrollment_code() for _ in range(20)}
    assert len(codes) == 20
