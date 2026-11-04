"""The protected application: an enterprise assistant that runs *after* the engine
allows a prompt, and only with the tools the decision's policy permits."""

import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from shield_api.demo import tools
from shield_engine import ChatMessage, ChatModel

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ToolInvocation:
    tool: str
    args: dict[str, Any]
    result: Any


@dataclass(frozen=True, slots=True)
class AssistantReply:
    text: str
    tool_calls: list[ToolInvocation] = field(default_factory=list)


class Assistant(Protocol):
    async def respond(self, prompt: str, allowed_tools: list[str]) -> AssistantReply: ...


class DemoAssistant:
    """Routes to allowed tools, then asks the first working LLM to answer.

    ``models`` are tried in order (e.g. Gemini, then Groq). With none
    configured, or all failing, it returns a canned reply so the demo still
    works offline.
    """

    def __init__(self, models: Sequence[ChatModel] = ()) -> None:
        self.models = list(models)

    async def respond(self, prompt: str, allowed_tools: list[str]) -> AssistantReply:
        calls = [
            ToolInvocation(tool.name, {"query": prompt}, await tools.execute(tool, prompt))
            for tool in tools.route(prompt, allowed_tools)
        ]

        system = (
            "You are AI S.H.I.E.L.D., an enterprise operations assistant. "
            f"Tools you are authorised to use: {', '.join(allowed_tools) or 'none'}. "
            "Answer concisely using the tool results provided. If the user asks for something "
            "that needs a tool you are not authorised to use, say it is not permitted."
        )
        context = "\n".join(f"[{c.tool}] {json.dumps(c.result)}" for c in calls)
        user = f"{prompt}\n\nTool results:\n{context}" if context else prompt
        messages = [ChatMessage("system", system), ChatMessage("user", user)]

        for model in self.models:
            try:
                return AssistantReply(await model.complete(messages, temperature=0.3), calls)
            except Exception:
                logger.warning("assistant model %s failed", type(model).__name__, exc_info=True)

        summary = f" Tools used: {', '.join(c.tool for c in calls)}." if calls else ""
        return AssistantReply(f"AI S.H.I.E.L.D. processed your request.{summary}", calls)
