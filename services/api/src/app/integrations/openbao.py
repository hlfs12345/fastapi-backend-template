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
        timeout_seconds: float,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        headers = {"X-Vault-Token": token} if token else None
        self._client = client or httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers=headers,
            timeout=timeout_seconds,
        )
        self._owns_client = client is None

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
        try:
            response = await self._client.post(path, json=payload)
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise OpenBaoError("OpenBao Transit operation failed.") from error

        data = body.get("data") if isinstance(body, dict) else None
        if not isinstance(data, dict):
            raise OpenBaoError("OpenBao returned an invalid response.")
        return data

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
