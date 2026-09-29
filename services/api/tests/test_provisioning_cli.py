from unittest.mock import AsyncMock, patch
from uuid import uuid4

from app.cli.provision_tenant import main
from app.services.provisioning import ProvisionedTenant


def test_cli_never_passes_password_on_command_line(capsys) -> None:
    provision = AsyncMock(
        return_value=ProvisionedTenant(
            tenant_id=uuid4(),
            user_id=uuid4(),
            tenant_user_id=uuid4(),
            owner_role_id=uuid4(),
            reused_user=False,
        )
    )
    with (
        patch("builtins.input", side_effect=["Tenant", "tenant", "user@example.com"]),
        patch("getpass.getpass", side_effect=["correct password", "correct password"]),
        patch("app.cli.provision_tenant._provision", provision),
    ):
        exit_code = main()

    output = capsys.readouterr()
    assert exit_code == 0
    assert "correct password" not in output.out
    assert "correct password" not in output.err
    provision.assert_awaited_once_with(
        tenant_name="Tenant",
        tenant_slug="tenant",
        email="user@example.com",
        password="correct password",
    )


def test_cli_rejects_password_confirmation_mismatch(capsys) -> None:
    provision = AsyncMock()
    with (
        patch("builtins.input", side_effect=["Tenant", "tenant", "user@example.com"]),
        patch("getpass.getpass", side_effect=["first password", "second password"]),
        patch("app.cli.provision_tenant._provision", provision),
    ):
        exit_code = main()

    output = capsys.readouterr()
    assert exit_code == 2
    assert "passwords do not match" in output.err
    assert "first password" not in output.err
    assert "second password" not in output.err
    provision.assert_not_awaited()
