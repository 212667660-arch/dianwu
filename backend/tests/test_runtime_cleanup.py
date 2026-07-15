import asyncio

from backend.services import db as repo
from backend.services import orchestrator


def test_close_runtime_clears_in_memory_state(monkeypatch) -> None:
    closed = []

    async def close_gateway() -> None:
        closed.append(True)

    async def exercise() -> None:
        orchestrator._generation_cancel_events["generation"] = asyncio.Event()
        orchestrator._workflow_locks["session"] = asyncio.Lock()
        repo._SESSION_LOCKS["session"] = repo.RLock()
        monkeypatch.setattr(orchestrator.model_runtime_router, "close", close_gateway)
        await orchestrator.close_runtime()

    asyncio.run(exercise())
    assert orchestrator._generation_cancel_events == {}
    assert orchestrator._workflow_locks == {}
    assert repo._SESSION_LOCKS == {}
    assert closed == [True]
