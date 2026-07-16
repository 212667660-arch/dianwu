from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from weakref import WeakKeyDictionary


_MODEL_CALL_SEMAPHORES: WeakKeyDictionary[
    asyncio.AbstractEventLoop,
    asyncio.Semaphore,
] = WeakKeyDictionary()


def _model_call_semaphore() -> asyncio.Semaphore:
    loop = asyncio.get_running_loop()
    semaphore = _MODEL_CALL_SEMAPHORES.get(loop)
    if semaphore is None:
        semaphore = asyncio.Semaphore(2)
        _MODEL_CALL_SEMAPHORES[loop] = semaphore
    return semaphore


@asynccontextmanager
async def model_call_slot():
    async with _model_call_semaphore():
        yield
