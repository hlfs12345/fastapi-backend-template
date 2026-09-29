from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.integrations.openbao import OpenBaoClient
from app.services.email_identity import EMAIL_SEARCH_CONTEXT, EmailIdentityProtector


@pytest.mark.asyncio
async def test_email_is_normalized_encrypted_and_blind_indexed() -> None:
    user_id = uuid4()
    openbao = AsyncMock(spec=OpenBaoClient)
    openbao.encrypt.return_value = "vault:v1:ciphertext"
    openbao.hmac.return_value = "vault:v1:hmac"
    protector = EmailIdentityProtector(openbao)

    protected = await protector.protect(user_id, "  USER@Example.COM ")

    assert protected.ciphertext == "vault:v1:ciphertext"
    assert protected.blind_index == "vault:v1:hmac"
    openbao.encrypt.assert_awaited_once_with(b"user@example.com", context=user_id.bytes)
    openbao.hmac.assert_awaited_once_with(
        b"user@example.com",
        context=EMAIL_SEARCH_CONTEXT,
    )


@pytest.mark.asyncio
async def test_global_email_search_uses_only_the_blind_index() -> None:
    openbao = AsyncMock(spec=OpenBaoClient)
    openbao.hmac.return_value = "vault:v1:hmac"
    protector = EmailIdentityProtector(openbao)

    assert await protector.blind_index("User@Example.com") == "vault:v1:hmac"
    openbao.hmac.assert_awaited_once_with(
        b"user@example.com",
        context=EMAIL_SEARCH_CONTEXT,
    )
