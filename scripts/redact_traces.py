"""Remove credentials from Playwright traces before CI uploads them.

Artifacts of a public repository are public, and a trace holds cookies, request
headers and typed text. Usage: python3 scripts/redact_traces.py <directory>
Standard library only.
"""

from __future__ import annotations

import json
import os
import sys
import zipfile
from pathlib import Path
from urllib.parse import quote, quote_plus

SECRET_VARIABLES = ("VERCEL_AUTOMATION_BYPASS_SECRET", "E2E_PASSWORD", "E2E_EMAIL")
SECRET_HEADERS = {"cookie", "set-cookie", "authorization", "x-vercel-protection-bypass"}
REDACTED = "REDACTED"


def redact_json(value: object) -> object:
    """Blank every cookie and credential header, at any depth."""
    if isinstance(value, list):
        return [redact_json(item) for item in value]
    if not isinstance(value, dict):
        return value
    if str(value.get("name", "")).lower() in SECRET_HEADERS and "value" in value:
        return {**value, "value": REDACTED}
    return {
        key: []
        if key == "cookies"
        else REDACTED
        if key.lower() in SECRET_HEADERS
        else redact_json(item)
        for key, item in value.items()
    }


def redact_member(name: str, data: bytes, secrets: list[str]) -> bytes:
    """Redact one file of a trace archive."""
    if name.endswith((".trace", ".network")):
        # A line that is not JSON fails the run: nothing unredacted is uploaded.
        lines = data.decode().split("\n")
        data = "\n".join(
            json.dumps(redact_json(json.loads(line))) if line.strip() else line for line in lines
        ).encode()
    for secret in secrets:
        forms = {secret, quote(secret, safe=""), quote_plus(secret), json.dumps(secret)[1:-1]}
        for form in sorted(forms, key=len, reverse=True):
            data = data.replace(form.encode(), REDACTED.encode())
    return data


def redact_archive(path: Path, secrets: list[str]) -> None:
    """Rewrite a trace archive without credentials."""
    with zipfile.ZipFile(path) as archive:
        members = [(name, archive.read(name)) for name in archive.namelist()]
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in members:
            archive.writestr(name, redact_member(name, data, secrets))


def main() -> int:
    """Redact every archive and page snapshot below the given directory."""
    if len(sys.argv) != 2:
        sys.stderr.write("usage: redact_traces.py <directory>\n")
        return 2
    secrets = [value for key in SECRET_VARIABLES if (value := os.environ.get(key))]
    for path in sorted(Path(sys.argv[1]).rglob("*.zip")):
        redact_archive(path, secrets)
    # Playwright writes the page text of a failure here.
    for path in sorted(Path(sys.argv[1]).rglob("*.md")):
        path.write_bytes(redact_member(path.name, path.read_bytes(), secrets))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
