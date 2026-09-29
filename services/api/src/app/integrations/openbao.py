import asyncio
import base64
from collections.abc import Mapping
from typing import Any

import httpx


class OpenBaoError(RuntimeError):
    pass


class OpenBaoClient:
    _HEALTHY_STATUS_CODES = {200, 429, 472, 473}

    def __init__(
        self,
        *,
        base_url: str,
        token: str | None,
        role_id: str | None = None,
        secret_id: str | None = None,
        timeout_seconds: float,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if (role_id is None) != (secret_id is None):
            raise ValueError("OpenBao AppRole credentials must be configured together.")
        headers = {"X-Vault-Token": token} if token else None
        self._client = client or httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers=headers,
            timeout=timeout_seconds,
        )
        self._owns_client = client is None
        self._role_id = role_id
        self._secret_id = secret_id
        self._auth_lock = asyncio.Lock()

    async def check_health(self) -> None:
        response = await self._client.get("/v1/sys/health")
        if response.status_code not in self._HEALTHY_STATUS_CODES:
            raise OpenBaoError("OpenBao is unavailable or sealed.")

    async def encrypt(self, plaintext: bytes, *, context: bytes) -> str:
        data = await self._transit_request(
            "/v1/transit/encrypt/pii-encryption",
            {"plaintext": _encode(plaintext), "context": _encode(context)},
        )
        return _required_string(data, "ciphertext")

    async def decrypt(self, ciphertext: str, *, context: bytes) -> bytes:
        data = await self._transit_request(
            "/v1/transit/decrypt/pii-encryption",
            {"ciphertext": ciphertext, "context": _encode(context)},
        )
        plaintext = _required_string(data, "plaintext")
        try:
            return base64.b64decode(plaintext, validate=True)
        except ValueError as error:
            raise OpenBaoError("OpenBao returned invalid plaintext data.") from error

    async def hmac(self, value: bytes, *, context: bytes) -> str:
        data = await self._transit_request(
            "/v1/transit/hmac/pii-search",
            {"input": _encode(value), "context": _encode(context)},
        )
        return _required_string(data, "hmac")

    async def _transit_request(self, path: str, payload: Mapping[str, str]) -> Mapping[str, Any]:
        await self._ensure_authenticated()
        try:
            response = await self._client.post(path, json=payload)
            if response.status_code == 403 and self._has_approle_credentials:
                failed_token = self._client.headers.get("X-Vault-Token")
                await self._authenticate_approle(previous_token=failed_token)
                response = await self._client.post(path, json=payload)
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise OpenBaoError("OpenBao Transit operation failed.") from error

        data = body.get("data") if isinstance(body, dict) else None
        if not isinstance(data, dict):
            raise OpenBaoError("OpenBao returned an invalid response.")
        return data

    @property
    def _has_approle_credentials(self) -> bool:
        return self._role_id is not None and self._secret_id is not None

    async def _ensure_authenticated(self) -> None:
        if "X-Vault-Token" not in self._client.headers and self._has_approle_credentials:
            await self._authenticate_approle(previous_token=None)

    async def _authenticate_approle(self, *, previous_token: str | None) -> None:
        async with self._auth_lock:
            current_token = self._client.headers.get("X-Vault-Token")
            if current_token is not None and current_token != previous_token:
                return
            try:
                response = await self._client.post(
                    "/v1/auth/approle/login",
                    json={"role_id": self._role_id, "secret_id": self._secret_id},
                )
                response.raise_for_status()
                body = response.json()
            except (httpx.HTTPError, ValueError) as error:
                raise OpenBaoError("OpenBao AppRole authentication failed.") from error

            auth = body.get("auth") if isinstance(body, dict) else None
            token = auth.get("client_token") if isinstance(auth, dict) else None
            if not isinstance(token, str) or not token:
                raise OpenBaoError("OpenBao returned an invalid authentication response.")
            self._client.headers["X-Vault-Token"] = token

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()


def _encode(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def _required_string(data: Mapping[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise OpenBaoError(f"OpenBao response is missing {key}.")
    return value
