from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from secrets import token_urlsafe
from uuid import UUID, uuid4

import jwt
from jwt.exceptions import InvalidTokenError
from pwdlib import PasswordHash
from pwdlib.exceptions import PwdlibError


class InvalidAccessTokenError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class AccessTokenClaims:
    user_id: UUID
    tenant_id: UUID
    tenant_user_id: UUID


class PasswordManager:
    def __init__(self) -> None:
        self._password_hash = PasswordHash.recommended()
        self._dummy_hash = self._password_hash.hash(token_urlsafe(32))

    def hash(self, password: str) -> str:
        return self._password_hash.hash(password)

    def verify_and_update(
        self, password: str, password_hash: str | None
    ) -> tuple[bool, str | None]:
        target_hash = password_hash or self._dummy_hash
        try:
            valid, updated_hash = self._password_hash.verify_and_update(password, target_hash)
        except PwdlibError:
            return False, None
        if password_hash is None:
            return False, None
        return valid, updated_hash


class AccessTokenCodec:
    _ALGORITHM = "HS256"

    def __init__(
        self,
        *,
        secret: str,
        issuer: str,
        audience: str,
        lifetime: timedelta,
    ) -> None:
        self._secret = secret
        self._issuer = issuer
        self._audience = audience
        self._lifetime = lifetime

    @property
    def expires_in_seconds(self) -> int:
        return int(self._lifetime.total_seconds())

    def encode(self, claims: AccessTokenClaims) -> str:
        issued_at = datetime.now(UTC)
        payload = {
            "iss": self._issuer,
            "aud": self._audience,
            "sub": str(claims.user_id),
            "tenant_id": str(claims.tenant_id),
            "tenant_user_id": str(claims.tenant_user_id),
            "type": "access",
            "iat": issued_at,
            "exp": issued_at + self._lifetime,
            "jti": str(uuid4()),
        }
        return jwt.encode(payload, self._secret, algorithm=self._ALGORITHM)

    def decode(self, token: str) -> AccessTokenClaims:
        try:
            payload = jwt.decode(
                token,
                self._secret,
                algorithms=[self._ALGORITHM],
                audience=self._audience,
                issuer=self._issuer,
                options={
                    "require": [
                        "iss",
                        "aud",
                        "sub",
                        "tenant_id",
                        "tenant_user_id",
                        "type",
                        "iat",
                        "exp",
                        "jti",
                    ]
                },
            )
            if payload["type"] != "access":
                raise InvalidAccessTokenError
            return AccessTokenClaims(
                user_id=UUID(payload["sub"]),
                tenant_id=UUID(payload["tenant_id"]),
                tenant_user_id=UUID(payload["tenant_user_id"]),
            )
        except (InvalidTokenError, KeyError, TypeError, ValueError) as error:
            raise InvalidAccessTokenError from error


@dataclass(frozen=True, slots=True)
class RefreshToken:
    plaintext: str
    digest: bytes


def generate_refresh_token() -> RefreshToken:
    plaintext = token_urlsafe(64)
    return RefreshToken(plaintext=plaintext, digest=hash_refresh_token(plaintext))


def hash_refresh_token(token: str) -> bytes:
    return sha256(token.encode("utf-8")).digest()
