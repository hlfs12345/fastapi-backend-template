import asyncio
import getpass
import sys

from app.core.config import get_settings
from app.core.errors import ApplicationError
from app.core.security import PasswordManager
from app.db.database import Database
from app.integrations.openbao import OpenBaoClient
from app.repositories.provisioning import ProvisioningRepository
from app.services.email_identity import EmailIdentityProtector
from app.services.provisioning import ProvisionedTenant, TenantProvisioningService


def main() -> int:
    tenant_name = input("Tenant name: ").strip()
    tenant_slug = input("Tenant slug: ").strip()
    email = input("User email: ").strip()
    password = getpass.getpass("Password: ")
    password_confirmation = getpass.getpass("Confirm password: ")
    if password != password_confirmation:
        print("Provisioning failed: passwords do not match.", file=sys.stderr)
        return 2

    try:
        result = asyncio.run(
            _provision(
                tenant_name=tenant_name,
                tenant_slug=tenant_slug,
                email=email,
                password=password,
            )
        )
    except ApplicationError as error:
        print(f"Provisioning failed: {error.message}", file=sys.stderr)
        return 1
    except Exception:
        print("Provisioning failed because an unexpected error occurred.", file=sys.stderr)
        return 1

    _print_result(result)
    return 0


async def _provision(
    *,
    tenant_name: str,
    tenant_slug: str,
    email: str,
    password: str,
) -> ProvisionedTenant:
    settings = get_settings()
    database = Database(settings.database_url.get_secret_value())
    openbao = OpenBaoClient(
        base_url=str(settings.openbao_url),
        token=(settings.openbao_token.get_secret_value() if settings.openbao_token else None),
        role_id=(settings.openbao_role_id.get_secret_value() if settings.openbao_role_id else None),
        secret_id=(
            settings.openbao_secret_id.get_secret_value() if settings.openbao_secret_id else None
        ),
        timeout_seconds=settings.dependency_timeout_seconds,
    )
    try:
        async with database.session_factory() as session:
            service = TenantProvisioningService(
                repository=ProvisioningRepository(session),
                email_protector=EmailIdentityProtector(openbao),
                password_manager=PasswordManager(),
            )
            return await service.provision(
                tenant_name=tenant_name,
                tenant_slug=tenant_slug,
                email=email,
                password=password,
            )
    finally:
        await asyncio.gather(database.close(), openbao.close())


def _print_result(result: ProvisionedTenant) -> None:
    print("Tenant provisioned successfully.")
    print(f"tenant_id={result.tenant_id}")
    print(f"user_id={result.user_id}")
    print(f"tenant_user_id={result.tenant_user_id}")
    print(f"owner_role_id={result.owner_role_id}")
    print(f"reused_user={str(result.reused_user).lower()}")


if __name__ == "__main__":
    raise SystemExit(main())
