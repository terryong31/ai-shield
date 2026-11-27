"""Gemini adapter for the game's AI Agent (standard tier)."""

from collections.abc import Sequence

from google import genai
from google.genai import types

from shield_engine import ChatCompletion, ChatMessage


class GeminiChatModel:
    def __init__(self, api_key: str, model: str) -> None:
        self._client = genai.Client(api_key=api_key)
        self.model = model

    async def complete(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> str:
        completion = await self.complete_with_usage(
            messages, temperature=temperature, max_tokens=max_tokens
        )
        return completion.text

    def _thinking_config(self, thinking: bool) -> types.ThinkingConfig | None:
        # Gemini 3 rejects thinking_budget=0; "minimal" is its off setting.
        if not self.model.startswith("gemini-3"):
            return None
        level = types.ThinkingLevel.MEDIUM if thinking else types.ThinkingLevel.MINIMAL
        return types.ThinkingConfig(thinking_level=level)

    async def complete_with_usage(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        thinking: bool = False,
    ) -> ChatCompletion:
        system = "\n\n".join(m.content for m in messages if m.role == "system") or None
        contents = [
            types.Content(
                role="model" if m.role == "assistant" else "user",
                parts=[types.Part(text=m.content)],
            )
            for m in messages
            if m.role != "system"
        ]
        response = await self._client.aio.models.generate_content(
            model=self.model,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system,
                temperature=temperature,
                max_output_tokens=max_tokens,
                thinking_config=self._thinking_config(thinking),
                # Every game prompt asks for JSON. Without JSON mode Gemini sometimes ends with
                # MALFORMED_FUNCTION_CALL and empty text. Gemma has no JSON mode.
                response_mime_type="application/json" if self.model.startswith("gemini") else None,
            ),
        )
        usage = response.usage_metadata
        return ChatCompletion(
            text=response.text or "",
            input_tokens=usage.prompt_token_count if usage else None,
            # Google bills thought tokens as output.
            output_tokens=(usage.candidates_token_count or 0) + (usage.thoughts_token_count or 0)
            if usage
            else None,
        )
