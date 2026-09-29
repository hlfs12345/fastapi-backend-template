import unicodedata
from dataclasses import dataclass
from uuid import UUID

from app.integrations.openbao import OpenBaoClient

EMAIL_SEARCH_CONTEXT = b"users:email"


def normalize_email(email: str) -> str:
    return unicodedata.normalize("NFKC", email).strip().casefold()


@dataclass(frozen=True, slots=True)
class ProtectedEmail:
    ciphertext: str
    blind_index: str


class EmailIdentityProtector:
    def __init__(self, openbao: OpenBaoClient) -> None:
        self._openbao = openbao

    async def blind_index(self, email: str) -> str:
        normalized = normalize_email(email).encode("utf-8")
        return await self._openbao.hmac(normalized, context=EMAIL_SEARCH_CONTEXT)

    async def protect(self, user_id: UUID, email: str) -> ProtectedEmail:
        normalized = normalize_email(email).encode("utf-8")
        ciphertext = await self._openbao.encrypt(normalized, context=user_id.bytes)
        blind_index = await self._openbao.hmac(normalized, context=EMAIL_SEARCH_CONTEXT)
        return ProtectedEmail(ciphertext=ciphertext, blind_index=blind_index)

    async def reveal(self, user_id: UUID, ciphertext: str) -> str:
        plaintext = await self._openbao.decrypt(ciphertext, context=user_id.bytes)
        return plaintext.decode("utf-8")
