"""The admin bootstrap script: grant and revoke `app_metadata.role = "admin"` (spec 0012)."""

import pytest

from shield_api.admin_cli import create_admin, main, revoke_admin

from .conftest import FakeAuthDirectory

PASSWORD = "a long admin password"


def directory_with(*emails: str) -> FakeAuthDirectory:
    directory = FakeAuthDirectory()
    for email in emails:
        directory.add(email, "old password", app_metadata={"provider": "email"})
    return directory


@pytest.mark.spec("API-CLEAR-019")
def test_create_makes_a_confirmed_admin_user() -> None:
    directory = directory_with()

    assert create_admin(directory.client().auth.admin, "New@Example.com", PASSWORD) == "created"

    user = directory.by_email("new@example.com")
    assert user is not None
    assert user.app_metadata["role"] == "admin"
    assert directory.passwords[user.id] == PASSWORD
    assert directory.email_confirmed[user.id] is True


@pytest.mark.spec("API-CLEAR-019")
def test_create_promotes_an_existing_user_and_keeps_its_metadata() -> None:
    directory = directory_with("player@example.com")
    # A long user list must still be searched past the first page.
    for n in range(250):
        directory.add(f"filler{n}@example.com", "x")

    result = create_admin(directory.client().auth.admin, "PLAYER@example.com", PASSWORD)

    assert result == "updated"
    assert len(directory.users) == 251
    user = directory.by_email("player@example.com")
    assert user is not None
    assert user.app_metadata == {"provider": "email", "role": "admin"}
    assert directory.passwords[user.id] == PASSWORD
    assert directory.email_confirmed[user.id] is True


@pytest.mark.spec("API-CLEAR-019")
def test_revoke_removes_only_the_role() -> None:
    directory = directory_with()
    admin = directory.client().auth.admin
    create_admin(admin, "boss@example.com", PASSWORD)

    assert revoke_admin(admin, "boss@example.com") is True

    user = directory.by_email("boss@example.com")
    assert user is not None
    assert "role" not in user.app_metadata
    assert revoke_admin(admin, "ghost@example.com") is False


@pytest.mark.spec("API-CLEAR-019")
def test_an_empty_password_is_refused_before_any_write() -> None:
    directory = directory_with()

    with pytest.raises(ValueError, match="password"):
        create_admin(directory.client().auth.admin, "boss@example.com", "   ")

    assert directory.writes == 0


@pytest.mark.spec("API-CLEAR-019")
def test_the_cli_prompts_for_the_password_and_never_prints_it(capsys) -> None:
    directory = directory_with()
    admin = directory.client().auth.admin
    prompts: list[str] = []

    def read_password(prompt: str) -> str:
        prompts.append(prompt)
        return PASSWORD

    assert main(["create", "boss@example.com"], admin=admin, read_password=read_password) == 0
    assert len(prompts) == 1
    assert main(["revoke", "boss@example.com"], admin=admin) == 0

    output = capsys.readouterr()
    assert PASSWORD not in output.out + output.err
    assert "boss@example.com" in output.out


@pytest.mark.spec("API-CLEAR-019")
@pytest.mark.parametrize(
    "argv",
    [["create", "boss@example.com", PASSWORD], ["create"], ["promote", "boss@example.com"], []],
)
def test_the_cli_rejects_bad_usage_without_writing(argv: list[str]) -> None:
    directory = directory_with()

    code = main(argv, admin=directory.client().auth.admin, read_password=lambda _: PASSWORD)

    assert code == 2
    assert directory.writes == 0


@pytest.mark.spec("API-CLEAR-019")
def test_the_cli_fails_on_an_unknown_email_or_an_empty_password() -> None:
    directory = directory_with()
    admin = directory.client().auth.admin

    assert main(["revoke", "ghost@example.com"], admin=admin) == 1
    assert main(["create", "boss@example.com"], admin=admin, read_password=lambda _: "") == 1
    assert directory.writes == 0
