from __future__ import annotations

import asyncio
from dataclasses import dataclass, field


@dataclass
class BundleCancellation:
    """Per-bundle cancellation signal management."""
    event: asyncio.Event = field(default_factory=asyncio.Event)
    cancelled: bool = False

    def cancel(self) -> None:
        self.cancelled = True
        self.event.set()

    def is_cancelled(self) -> bool:
        return self.cancelled

    async def wait_if_not_cancelled(self) -> bool:
        """Wait for cancel signal. Returns True if cancelled."""
        if self.cancelled:
            return True
        await self.event.wait()
        return self.cancelled


# Global bundle_id -> cancellation mapping
_bundle_cancellations: dict[str, BundleCancellation] = {}


def get_or_create_cancellation(bundle_id: str) -> BundleCancellation:
    if bundle_id not in _bundle_cancellations:
        _bundle_cancellations[bundle_id] = BundleCancellation()
    return _bundle_cancellations[bundle_id]


def cancel_bundle(bundle_id: str) -> None:
    cancellation = _bundle_cancellations.get(bundle_id)
    if cancellation is not None:
        cancellation.cancel()


def cleanup_cancellation(bundle_id: str) -> None:
    _bundle_cancellations.pop(bundle_id, None)
