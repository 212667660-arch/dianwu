from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager


_MODEL_CALL_SEMAPHORE = asyncio.Semaphore(2)


@asynccontextmanager
async def model_call_slot():
    async with _MODEL_CALL_SEMAPHORE:
        yield
