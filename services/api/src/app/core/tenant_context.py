from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class TenantContext:
    tenant_id: UUID
    user_id: UUID
    tenant_user_id: UUID
    permissions: frozenset[str] = frozenset()
    pending_legal_version_ids: tuple[UUID, ...] = ()
