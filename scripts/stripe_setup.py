"""Store Stripe keys in Infisical for dev and prod (spec 0049). Run by a person.

The key is typed at a hidden prompt. No value is printed.
"""

from __future__ import annotations

import getpass
import json
import os
import subprocess
import sys

EVENTS = (
    "checkout.session.completed",
    "checkout.session.async_payment_succeeded",
    "checkout.session.async_payment_failed",
    "checkout.session.expired",
    "charge.refunded",
    "refund.failed",
    "refund.updated",
    "charge.dispute.funds_withdrawn",
    "charge.dispute.funds_reinstated",
)


def _run(args: list[str], env: dict[str, str] | None = None, stdin: str | None = None) -> str:
    done = subprocess.run(args, input=stdin, capture_output=True, text=True, check=False, env=env)
    if done.returncode != 0:
        # Output can hold secrets, so it is not shown.
        raise SystemExit(f"`{args[0]} {args[1]}` failed with exit code {done.returncode}.")
    return done.stdout.strip()


def _store(environment: str, key: str, webhook_secret: str) -> None:
    # Through stdin: the values are never on disk or in the process list.
    _run(
        [
            "infisical",
            "secrets",
            "set",
            "--file=/dev/stdin",
            f"--env={environment}",
            "--path=/api",
            "--silent",
        ],
        stdin=f"STRIPE_SECRET_KEY={key}\nSTRIPE_WEBHOOK_SECRET={webhook_secret}\n",
    )
    print(f"Stored both Stripe variables in Infisical {environment} /api.")


def _update_events(endpoint: str) -> int:
    env = {**os.environ, "STRIPE_API_KEY": os.environ["STRIPE_SECRET_KEY"]}
    listing = json.loads(_run(["stripe", "webhook_endpoints", "list", "--limit", "100"], env))
    found = [item["id"] for item in listing.get("data", []) if item.get("url") == endpoint]
    if not found:
        print(f"No webhook endpoint for {endpoint}.", file=sys.stderr)
        return 1
    flags = [flag for event in EVENTS for flag in ("--enabled-events", event)]
    for webhook_id in found:
        _run(["stripe", "webhook_endpoints", "update", webhook_id, *flags], env)
    print(f"Updated the events of {endpoint}.")
    return 0


def main() -> int:
    web_url = sys.argv[1].strip().rstrip("/") if len(sys.argv) > 1 else ""
    if not web_url.startswith("https://"):
        print("Usage: mise run stripe:setup https://<production web URL>", file=sys.stderr)
        return 2
    endpoint = f"{web_url}/api/v1/billing/webhook"
    if "--events" in sys.argv:
        return _update_events(endpoint)
    key = getpass.getpass("Stripe sandbox secret key (sk_test_... or rk_test_...): ").strip()
    if not key.startswith(("sk_test_", "rk_test_")):
        print("That is not a sandbox key.", file=sys.stderr)
        return 2
    env = {**os.environ, "STRIPE_API_KEY": key}

    local_hook = _run(["stripe", "listen", "--print-secret"], env)
    _store("dev", key, local_hook)

    listing = json.loads(_run(["stripe", "webhook_endpoints", "list", "--limit", "100"], env))
    if any(item.get("url") == endpoint for item in listing.get("data", [])):
        print(
            f"The endpoint {endpoint} exists and Stripe shows its secret only once. "
            "Delete it in the Stripe dashboard and run this again.",
            file=sys.stderr,
        )
        return 1
    flags = [flag for event in EVENTS for flag in ("--enabled-events", event)]
    created = json.loads(
        _run(["stripe", "webhook_endpoints", "create", "--url", endpoint, *flags], env)
    )
    _store("prod", key, str(created["secret"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
