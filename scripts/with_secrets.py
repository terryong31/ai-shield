"""Run a dev command with Infisical secrets when signed in, else run it directly (spec 0055).

Usage: python3 scripts/with_secrets.py --env=dev --path=/api -- <command> [args...]

New contributors have no access to the team's Infisical project. Without a signed-in
Infisical session the command still starts, with the optional overrides in the app's
`.env` file and the game's offline defaults for any provider key that is not set.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys

NOTICE = (
    "Infisical is not installed or not signed in; starting without team secrets. "
    "Optional overrides go in the app's .env file (see .env.example)."
)


def infisical_ready() -> bool:
    """True when the Infisical CLI exists and has a session or a machine token."""
    executable = shutil.which("infisical")
    if executable is None:
        return False
    if os.environ.get("INFISICAL_TOKEN"):
        return True
    try:
        # The token goes to /dev/null: only the exit code is needed.
        result = subprocess.run(
            [executable, "user", "get", "token"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def main(argv: list[str]) -> int:
    if "--" not in argv:
        print("usage: with_secrets.py --env=ENV --path=PATH -- COMMAND...", file=sys.stderr)
        return 2
    split = argv.index("--")
    parser = argparse.ArgumentParser(prog="with_secrets.py")
    parser.add_argument("--env", required=True)
    parser.add_argument("--path", required=True)
    options = parser.parse_args(argv[:split])
    command = argv[split + 1 :]
    if not command:
        print("with_secrets.py: no command to run", file=sys.stderr)
        return 2

    if infisical_ready():
        # Replacing this process keeps signals and exit codes with the real command.
        os.execvp(  # noqa: S606 - the command comes from mise.toml, not from a user
            "infisical",
            ["infisical", "run", f"--env={options.env}", f"--path={options.path}", "--", *command],
        )
    print(NOTICE, file=sys.stderr)
    os.execvp(command[0], command)  # noqa: S606 - the command comes from mise.toml
    return 0  # pragma: no cover - execvp does not return


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
