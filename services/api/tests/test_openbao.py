import base64

import httpx
import pytest

from app.integrations.openbao import OpenBaoClient, OpenBaoError


@pytest.mark.asyncio
async def test_encrypt_uses_transit_key_and_tenant_context() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/transit/encrypt/pii-encryption"
        assert request.headers["X-Vault-Token"] == "restricted-token"
        body = request.read()
        assert b'"plaintext":"c2Vuc2l0aXZl"' in body
        assert b'"context":"dGVuYW50LWlk"' in body
        return httpx.Response(200, json={"data": {"ciphertext": "vault:v1:ciphertext"}})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://openbao.test",
        headers={"X-Vault-Token": "restricted-token"},
    ) as http_client:
        client = OpenBaoClient(
            base_url="http://openbao.test",
            token=None,
            timeout_seconds=1,
            client=http_client,
        )
        ciphertext = await client.encrypt(b"sensitive", context=b"tenant-id")

    assert ciphertext == "vault:v1:ciphertext"


@pytest.mark.asyncio
async def test_decrypt_rejects_invalid_openbao_response() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"data": {"plaintext": "not base64!"}})
    )
    async with httpx.AsyncClient(
        transport=transport, base_url="http://openbao.test"
    ) as http_client:
        client = OpenBaoClient(
            base_url="http://openbao.test",
            token=None,
            timeout_seconds=1,
            client=http_client,
        )
        with pytest.raises(OpenBaoError, match="invalid plaintext"):
            await client.decrypt("vault:v1:ciphertext", context=b"tenant-id")


@pytest.mark.asyncio
async def test_decrypt_decodes_plaintext() -> None:
    encoded = base64.b64encode(b"clear value").decode("ascii")
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"data": {"plaintext": encoded}})
    )
    async with httpx.AsyncClient(
        transport=transport, base_url="http://openbao.test"
    ) as http_client:
        client = OpenBaoClient(
            base_url="http://openbao.test",
            token=None,
            timeout_seconds=1,
            client=http_client,
        )
        assert await client.decrypt("vault:v1:ciphertext", context=b"tenant-id") == b"clear value"
