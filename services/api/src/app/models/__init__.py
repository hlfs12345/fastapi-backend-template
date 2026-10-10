from sqlalchemy import MetaData

from app.db.base import Base
from app.models.contact import Contact
from app.models.contact_pii import ContactPii
from app.models.legal_acceptance import LegalAcceptance
from app.models.legal_document import LegalDocument
from app.models.legal_document_version import LegalDocumentVersion
from app.models.permission import Permission
from app.models.refresh_session import RefreshSession
from app.models.role import Role
from app.models.role_permission import RolePermission
from app.models.tenant import Tenant
from app.models.tenant_user import TenantUser
from app.models.tenant_user_role import TenantUserRole
from app.models.user import User

metadata: MetaData = Base.metadata

__all__ = [
    "Contact",
    "ContactPii",
    "Permission",
    "LegalAcceptance",
    "LegalDocument",
    "LegalDocumentVersion",
    "RefreshSession",
    "Role",
    "RolePermission",
    "Tenant",
    "TenantUser",
    "TenantUserRole",
    "User",
    "metadata",
]
