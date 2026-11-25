import json
import zipfile
from pathlib import Path

import redact_traces


def test_trace_keeps_no_cookies_credential_headers_or_secret_values(tmp_path: Path) -> None:
    trace = tmp_path / "trace.zip"
    request = {
        "cookies": [{"name": "shield_session", "value": "session-token"}],
        "headers": [
            {"name": "Cookie", "value": "_vercel_jwt=jwt-token"},
            {"name": "Accept", "value": "application/json"},
        ],
    }
    with zipfile.ZipFile(trace, "w") as archive:
        archive.writestr("0-trace.network", json.dumps({"snapshot": {"request": request}}) + "\n")
        archive.writestr("0-trace.trace", json.dumps({"params": {"value": 'p"ss w'}}) + "\n")
        archive.writestr("resources/body", json.dumps({"password": 'p"ss w'}))
        archive.writestr("resources/form", "password=p%22ss+w")

    redact_traces.redact_archive(trace, ['p"ss w'])

    with zipfile.ZipFile(trace) as archive:
        text = "".join(archive.read(name).decode() for name in archive.namelist())
    for leaked in ("session-token", "jwt-token", 'p\\"ss w', "p%22ss+w"):
        assert leaked not in text
    assert "application/json" in text
