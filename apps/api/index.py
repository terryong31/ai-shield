"""Vercel entrypoint.

Vercel installs this project's dependencies but not the project itself, so the
``src/`` layout package is not importable. Put ``src/`` on the path, then expose
the same ASGI app that uvicorn serves elsewhere.
"""

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from shield_api.main import app  # noqa: E402

__all__ = ["app"]
