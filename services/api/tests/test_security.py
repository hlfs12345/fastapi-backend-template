from datetime import timedelta
from uuid import uuid4

import pytest

from app.core.security import (
    AccessTokenClaims,
    AccessTokenCodec,
    InvalidAccessTokenError,
    PasswordManager,
    generate_refresh_token,
    hash_refresh_token,
)


def _access_tokens() -> AccessTokenCodec:
    return AccessTokenCodec(
        secret="test-only-jwt-secret-with-at-least-32-characters",
        issuer="edisk-api",
        audience="edisk-app",
        lifetime=timedelta(minutes=15),
    )


def test_passwords_use_argon2id_and_verify_without_plaintext_storage() -> None:
    passwords = PasswordManager()
    encoded = passwords.hash("correct horse battery staple")

    assert encoded.startswith("$argon2id$")
    assert passwords.verify_and_update("correct horse battery staple", encoded)[0]
    assert not passwords.verify_and_update("wrong password", encoded)[0]
    assert not passwords.verify_and_update("unknown account password", None)[0]


def test_access_token_round_trip_preserves_authorized_tenant_claims() -> None:
    codec = _access_tokens()
    expected = AccessTokenClaims(
        user_id=uuid4(),
        tenant_id=uuid4(),
        tenant_user_id=uuid4(),
    )

    assert codec.decode(codec.encode(expected)) == expected


def test_access_token_rejects_tampering() -> None:
    codec = _access_tokens()
    token = codec.encode(
        AccessTokenClaims(
            user_id=uuid4(),
            tenant_id=uuid4(),
            tenant_user_id=uuid4(),
        )
    )

    with pytest.raises(InvalidAccessTokenError):
        codec.decode(f"{token[:-1]}x")


def test_refresh_tokens_are_random_and_only_compared_by_digest() -> None:
    first = generate_refresh_token()
    second = generate_refresh_token()

    assert first.plaintext != second.plaintext
    assert first.digest != second.digest
    assert len(first.digest) == 32
    assert hash_refresh_token(first.plaintext) == first.digest
