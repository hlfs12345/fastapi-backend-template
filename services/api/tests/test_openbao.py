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


@pytest.mark.asyncio
async def test_hmac_uses_search_key_and_context() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/transit/hmac/pii-search"
        body = request.read()
        assert b'"input":"dXNlckBleGFtcGxlLmNvbQ=="' in body
        assert b'"context":"dXNlcnM6ZW1haWw="' in body
        return httpx.Response(200, json={"data": {"hmac": "vault:v1:hmac"}})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://openbao.test",
    ) as http_client:
        client = OpenBaoClient(
            base_url="http://openbao.test",
            token=None,
            timeout_seconds=1,
            client=http_client,
        )
        result = await client.hmac(b"user@example.com", context=b"users:email")

    assert result == "vault:v1:hmac"


@pytest.mark.asyncio
async def test_transit_authenticates_with_restricted_approle() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/auth/approle/login":
            body = request.read()
            assert b'"role_id":"role-id"' in body
            assert b'"secret_id":"secret-id"' in body
            return httpx.Response(200, json={"auth": {"client_token": "restricted-token"}})
        assert request.url.path == "/v1/transit/hmac/pii-search"
        assert request.headers["X-Vault-Token"] == "restricted-token"
        return httpx.Response(200, json={"data": {"hmac": "vault:v1:hmac"}})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://openbao.test",
    ) as http_client:
        client = OpenBaoClient(
            base_url="http://openbao.test",
            token=None,
            role_id="role-id",
            secret_id="secret-id",
            timeout_seconds=1,
            client=http_client,
        )
        result = await client.hmac(b"value", context=b"users:email")

    assert result == "vault:v1:hmac"


@pytest.mark.asyncio
async def test_transit_reauthenticates_after_token_is_rejected() -> None:
    login_count = 0
    transit_count = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal login_count, transit_count
        if request.url.path == "/v1/auth/approle/login":
            login_count += 1
            return httpx.Response(
                200,
                json={"auth": {"client_token": f"restricted-token-{login_count}"}},
            )
        transit_count += 1
        if transit_count == 1:
            return httpx.Response(403)
        assert request.headers["X-Vault-Token"] == "restricted-token-2"
        return httpx.Response(200, json={"data": {"hmac": "vault:v1:hmac"}})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://openbao.test",
    ) as http_client:
        client = OpenBaoClient(
            base_url="http://openbao.test",
            token=None,
            role_id="role-id",
            secret_id="secret-id",
            timeout_seconds=1,
            client=http_client,
        )
        result = await client.hmac(b"value", context=b"users:email")

    assert result == "vault:v1:hmac"
    assert login_count == 2
    assert transit_count == 2


def test_approle_credentials_must_be_configured_as_a_pair() -> None:
    with pytest.raises(ValueError, match="configured together"):
        OpenBaoClient(
            base_url="http://openbao.test",
            token=None,
            role_id="role-id",
            timeout_seconds=1,
        )
