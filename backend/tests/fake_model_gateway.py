from __future__ import annotations

from collections.abc import AsyncIterator


class ScriptedGateway:
    def __init__(
        self,
        completions: list[object] | None = None,
        streams: list[list[object]] | None = None,
    ) -> None:
        self.completions = list(completions or [])
        self.streams = list(streams or [])
        self.calls: list[dict[str, object]] = []
        self.closed = False

    async def complete(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.2,
        *,
        model_name: str | None = None,
        reasoning: dict[str, object] | None = None,
        max_output_tokens: int = 4096,
    ) -> str:
        self.calls.append({
            "kind": "complete",
            "messages": [dict(message) for message in messages],
            "temperature": temperature,
            "model_name": model_name,
            "reasoning": dict(reasoning or {}),
            "max_output_tokens": max_output_tokens,
        })
        if not self.completions:
            raise AssertionError("scripted completion queue is empty")
        value = self.completions.pop(0)
        if isinstance(value, BaseException):
            raise value
        return str(value)

    async def stream(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.2,
        *,
        model_name: str | None = None,
        reasoning: dict[str, object] | None = None,
        max_output_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        self.calls.append({
            "kind": "stream",
            "messages": [dict(message) for message in messages],
            "temperature": temperature,
            "model_name": model_name,
            "reasoning": dict(reasoning or {}),
            "max_output_tokens": max_output_tokens,
        })
        if not self.streams:
            raise AssertionError("scripted stream queue is empty")
        for value in self.streams.pop(0):
            if isinstance(value, BaseException):
                raise value
            yield str(value)

    async def aclose(self) -> None:
        self.closed = True
