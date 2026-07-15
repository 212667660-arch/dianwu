from __future__ import annotations

from typing import Literal, TypeAlias


ReasoningEffort: TypeAlias = Literal["auto", "off", "low", "medium", "high", "xhigh"]
ReasoningAdapter: TypeAlias = Literal[
    "none",
    "openai_reasoning_effort",
    "anthropic_thinking",
]

_ORDER: tuple[ReasoningEffort, ...] = ("off", "low", "medium", "high", "xhigh")
_ANTHROPIC_BUDGETS: dict[ReasoningEffort, int] = {
    "low": 1024,
    "medium": 4096,
    "high": 8192,
    "xhigh": 16384,
}


def effective_effort(
    requested: ReasoningEffort,
    supported: list[ReasoningEffort],
) -> ReasoningEffort:
    if requested == "auto":
        return "auto"
    if requested in supported:
        return requested
    requested_index = _ORDER.index(requested)
    candidates = [
        value
        for value in supported
        if value in _ORDER and _ORDER.index(value) < requested_index
    ]
    return candidates[-1] if candidates else "off"


def reasoning_payload(
    adapter: ReasoningAdapter,
    effort: ReasoningEffort,
) -> dict[str, object]:
    if adapter == "none" or effort in {"auto", "off"}:
        return {}
    if adapter == "openai_reasoning_effort":
        return {"reasoning_effort": effort}
    return {
        "thinking": {
            "type": "enabled",
            "budget_tokens": _ANTHROPIC_BUDGETS[effort],
        }
    }
