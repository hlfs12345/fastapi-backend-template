import asyncio
import re
import unicodedata
from dataclasses import dataclass
from uuid import UUID

from app.integrations.openbao import OpenBaoClient
from app.services.email_identity import normalize_email

_PHONE_FORMATTING = frozenset(" ()-.")
_E164_PATTERN = re.compile(r"^\+[1-9][0-9]{3,14}$")


def normalize_contact_name(name: str) -> str:
    return unicodedata.normalize("NFKC", name).strip()


def normalize_phone(phone: str) -> str:
    value = unicodedata.normalize("NFKC", phone).strip()
    if not value.startswith("+"):
        raise ValueError("phone_country_code_required")
    significant_characters = (
        character for character in value[1:] if character not in _PHONE_FORMATTING
    )
    digits = "".join(significant_characters)
    canonical = "+" + digits
    if not _E164_PATTERN.fullmatch(canonical):
        raise ValueError("invalid_phone_number")
    return canonical


@dataclass(frozen=True, slots=True)
class ProtectedValue:
    plaintext: str
    ciphertext: str
    blind_index: str | None = None


@dataclass(frozen=True, slots=True)
class RevealedContactData:
    name: str
    email: str | None
    phone: str | None


class ContactDataProtector:
    def __init__(self, openbao: OpenBaoClient) -> None:
        self._openbao = openbao

    async def protect_name(
        self,
        *,
        tenant_id: UUID,
        contact_id: UUID,
        name: str,
    ) -> ProtectedValue:
        normalized = normalize_contact_name(name)
        ciphertext = await self._openbao.encrypt(
            normalized.encode("utf-8"),
            context=_encryption_context(tenant_id, contact_id, "name"),
        )
        return ProtectedValue(plaintext=normalized, ciphertext=ciphertext)

    async def protect_email(
        self,
        *,
        tenant_id: UUID,
        contact_id: UUID,
        email: str,
    ) -> ProtectedValue:
        normalized = normalize_email(email)
        encoded = normalized.encode("utf-8")
        ciphertext, blind_index = await asyncio.gather(
            self._openbao.encrypt(
                encoded,
                context=_encryption_context(tenant_id, contact_id, "email"),
            ),
            self._openbao.hmac(encoded, context=_search_context(tenant_id, "email")),
        )
        return ProtectedValue(
            plaintext=normalized,
            ciphertext=ciphertext,
            blind_index=blind_index,
        )

    async def protect_phone(
        self,
        *,
        tenant_id: UUID,
        contact_id: UUID,
        phone: str,
    ) -> ProtectedValue:
        normalized = normalize_phone(phone)
        encoded = normalized.encode("utf-8")
        ciphertext, blind_index = await asyncio.gather(
            self._openbao.encrypt(
                encoded,
                context=_encryption_context(tenant_id, contact_id, "phone"),
            ),
            self._openbao.hmac(encoded, context=_search_context(tenant_id, "phone")),
        )
        return ProtectedValue(
            plaintext=normalized,
            ciphertext=ciphertext,
            blind_index=blind_index,
        )

    async def email_blind_index(self, *, tenant_id: UUID, email: str) -> str:
        normalized = normalize_email(email).encode("utf-8")
        return await self._openbao.hmac(normalized, context=_search_context(tenant_id, "email"))

    async def phone_blind_index(self, *, tenant_id: UUID, phone: str) -> str:
        normalized = normalize_phone(phone).encode("utf-8")
        return await self._openbao.hmac(normalized, context=_search_context(tenant_id, "phone"))

    async def reveal(
        self,
        *,
        tenant_id: UUID,
        contact_id: UUID,
        name_ciphertext: str,
        email_ciphertext: str | None,
        phone_ciphertext: str | None,
    ) -> RevealedContactData:
        fields: list[tuple[str, str]] = [("name", name_ciphertext)]
        if email_ciphertext is not None:
            fields.append(("email", email_ciphertext))
        if phone_ciphertext is not None:
            fields.append(("phone", phone_ciphertext))
        plaintexts = await asyncio.gather(
            *(
                self._openbao.decrypt(
                    ciphertext,
                    context=_encryption_context(tenant_id, contact_id, field),
                )
                for field, ciphertext in fields
            )
        )
        values = {
            field: plaintext.decode("utf-8")
            for (field, _), plaintext in zip(fields, plaintexts, strict=True)
        }
        return RevealedContactData(
            name=values["name"],
            email=values.get("email"),
            phone=values.get("phone"),
        )


def _encryption_context(tenant_id: UUID, contact_id: UUID, field: str) -> bytes:
    return b"contacts:pii:" + tenant_id.bytes + contact_id.bytes + field.encode("ascii")


def _search_context(tenant_id: UUID, field: str) -> bytes:
    return b"contacts:search:" + tenant_id.bytes + field.encode("ascii")
