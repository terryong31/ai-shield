"""AI S.H.I.E.L.D. engine: the checks behind the prompt-injection defence game.

Typical use::

    from shield_engine.game import run_wave
    from shield_engine.models import load_baseline

    result = await run_wave(board, level_id="easy", classifier=load_baseline())
"""

from importlib.metadata import PackageNotFoundError, version

from shield_engine.detectors import ClassifierDetector
from shield_engine.ports import ChatCompletion, ChatMessage, ChatModel, UsageChatModel
from shield_engine.types import Signal, Verdict
from shield_engine.untrusted import wrap_untrusted

try:
    __version__ = version("shield-engine")
except PackageNotFoundError:  # pragma: no cover - running from a source checkout
    __version__ = "0.0.0+unknown"

__all__ = [
    "ChatCompletion",
    "ChatMessage",
    "ChatModel",
    "ClassifierDetector",
    "Signal",
    "UsageChatModel",
    "Verdict",
    "__version__",
    "wrap_untrusted",
]
