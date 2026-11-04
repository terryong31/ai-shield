"""Export the OpenAPI contract: ``uv run shield-api-export-openapi [path]``."""

import json
import sys
from pathlib import Path

from shield_api.main import create_app
from shield_api.settings import Settings

DEFAULT_PATH = Path(__file__).resolve().parents[4] / "contracts" / "shield-api.openapi.json"


def render() -> str:
    # Defaults only, so a developer's .env cannot leak into the contract.
    schema = create_app(settings=Settings(_env_file=None)).openapi()  # type: ignore[call-arg]
    return json.dumps(schema, indent=2, sort_keys=True) + "\n"


def main() -> None:
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render(), encoding="utf-8")
    print(f"wrote {target}")
