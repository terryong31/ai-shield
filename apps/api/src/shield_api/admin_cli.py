"""Grant or revoke admin access to the `/_console` (spec 0012, API-CLEAR-019).

An admin is a Supabase Auth user whose ``app_metadata.role`` is ``"admin"``.
Signing up never grants it; only this script does, with the service key.

    mise run admin:create you@example.com    # prompts for the password
    mise run admin:revoke you@example.com

The password is read from a prompt (or stdin when piped), never from the
command line, so it stays out of shell history and process listings.
"""

import getpass
import sys
from collections.abc import Callable, Sequence
from typing import Any

from shield_api.services.admins import ADMIN_ROLE

PAGE_SIZE = 200
USAGE = "usage: python -m shield_api.admin_cli {create,revoke} <email>"


def _find_user(admin: Any, email: str) -> Any | None:
    page = 1
    while True:
        users = admin.list_users(page=page, per_page=PAGE_SIZE)
        users = users if isinstance(users, list) else getattr(users, "users", [])
        for user in users:
            if (user.email or "").lower() == email:
                return user
        if len(users) < PAGE_SIZE:
            return None
        page += 1


def create_admin(admin: Any, email: str, password: str) -> str:
    """Create the user as an admin, or promote an existing one. Returns what happened."""
    if not password.strip():
        raise ValueError("password must not be empty")
    email = email.strip().lower()
    existing = _find_user(admin, email)
    if existing is None:
        admin.create_user(
            {
                "email": email,
                "password": password,
                "email_confirm": True,
                "app_metadata": {"role": ADMIN_ROLE},
            }
        )
        return "created"
    metadata = {**(existing.app_metadata or {}), "role": ADMIN_ROLE}
    admin.update_user_by_id(
        existing.id, {"password": password, "email_confirm": True, "app_metadata": metadata}
    )
    return "updated"


def revoke_admin(admin: Any, email: str) -> bool:
    """Remove the admin role. ``False`` when no user has that email."""
    user = _find_user(admin, email.strip().lower())
    if user is None:
        return False
    metadata = {k: v for k, v in (user.app_metadata or {}).items() if k != "role"}
    admin.update_user_by_id(user.id, {"app_metadata": metadata})
    return True


def _supabase_admin() -> Any:
    from shield_api.settings import Settings
    from supabase import create_client

    settings = Settings()
    if not (settings.SUPABASE_URL and settings.SUPABASE_KEY):
        raise SystemExit("SUPABASE_URL and SUPABASE_KEY (the service key) must be set.")
    client = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY.get_secret_value())
    return client.auth.admin


def main(
    argv: Sequence[str] | None = None,
    *,
    admin: Any | None = None,
    read_password: Callable[[str], str] = getpass.getpass,
) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 2 or args[0] not in ("create", "revoke"):
        print(USAGE, file=sys.stderr)
        return 2
    action, email = args[0], args[1].strip().lower()

    if action == "create":
        password = read_password(f"Password for {email}: ")
        if not password.strip():
            print("The password must not be empty.", file=sys.stderr)
            return 1
        result = create_admin(admin or _supabase_admin(), email, password)
        print(f"{result.capitalize()} {email} with role=admin.")
        print("Sign in at /_console with this email and password.")
        return 0

    if not revoke_admin(admin or _supabase_admin(), email):
        print(f"No Supabase Auth user has the email {email}.", file=sys.stderr)
        return 1
    print(f"Revoked admin from {email}. Open sessions end when they expire or sign out.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
