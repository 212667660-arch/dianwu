from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import threading

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.database import Base
from backend.knowledge.chunking import chunk_blocks
from backend.knowledge.import_service import KnowledgeImportCoordinator
from backend.knowledge.object_store import KnowledgeObjectStore
from backend.knowledge.optional_packs import APP_VERSION
from backend.knowledge.parsers import StructuredBlock
from backend.knowledge.repository import KnowledgeRepository
from backend.knowledge.search import KnowledgeSearchRepository
from backend.knowledge.search import KnowledgeUnavailable
from backend.knowledge.service import KnowledgeService
from backend.main import app
from backend.routers.knowledge import get_knowledge_service
from backend.tests.error_assertions import assert_error


class FakeCoordinator:
    def __init__(self) -> None:
        self.enqueued: list[int] = []
        self.cancelled: list[int] = []

    def enqueue(self, job_id: int) -> None:
        self.enqueued.append(job_id)

    async def cancel(self, job_id: int):
        self.cancelled.append(job_id)
        return None


@pytest.fixture()
def api(tmp_path: Path):
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record) -> None:
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    db = Session(engine)
    root = tmp_path / "knowledge"
    store = KnowledgeObjectStore(root)
    store.ensure_directories()
    repository = KnowledgeRepository(db, root)
    search = KnowledgeSearchRepository(db)
    search.ensure_schema()
    coordinator = FakeCoordinator()
    service = KnowledgeService(
        repository,
        store,
        search,
        coordinator,
        session_factory=lambda: Session(engine),
    )
    app.dependency_overrides[get_knowledge_service] = lambda: service
    try:
        with TestClient(app) as client:
            yield client, service, coordinator, root
    finally:
        app.dependency_overrides.pop(get_knowledge_service, None)
        db.close()
        engine.dispose()


def create_collection(client: TestClient, name: str = "高数") -> dict[str, object]:
    response = client.post(
        "/api/knowledge/collections",
        json={"name": name, "description": "本地资料", "color": "#c98f65"},
    )
    assert response.status_code == 201
    return response.json()


def write_object(root: Path, content: str) -> dict[str, object]:
    raw = content.encode("utf-8")
    digest = sha256(raw).hexdigest()
    (root / "objects" / digest).write_bytes(raw)
    return {
        "sha256": digest,
        "display_name": "讲义.txt",
        "extension": ".txt",
        "mime_type": "text/plain",
        "byte_size": len(raw),
        "object_relpath": f"objects/{digest}",
    }


def test_collection_crud_and_status(api) -> None:
    client, _service, _coordinator, _root = api
    collection = create_collection(client)

    listed = client.get("/api/knowledge/collections")
    updated = client.put(
        f"/api/knowledge/collections/{collection['id']}",
        json={"name": "高等数学", "color": "#8f9d7a"},
    )
    status = client.get("/api/knowledge/status")
    deleted = client.delete(f"/api/knowledge/collections/{collection['id']}")

    assert listed.status_code == 200
    assert [item["name"] for item in listed.json()] == ["高数"]
    assert updated.status_code == 200
    assert updated.json()["name"] == "高等数学"
    assert status.status_code == 200
    assert status.json()["fts"]["available"] is True
    assert deleted.status_code == 204


def test_knowledge_status_reports_verified_local_ocr_pack(api) -> None:
    client, _service, _coordinator, root = api
    pack_root = root / "packs" / "ocr"
    pack_root.mkdir(parents=True)
    payload = b"local-ocr-model"
    (pack_root / "model.bin").write_bytes(payload)
    major, minor, _patch = APP_VERSION.split(".")
    (pack_root / "manifest.json").write_text(
        json.dumps(
            {
                "kind": "ocr",
                "version": "1.0.0",
                "a3_compatibility": f">={major}.{minor},<{major}.{int(minor) + 1}",
                "license_spdx": "Apache-2.0",
                "files": [
                    {
                        "path": "model.bin",
                        "sha256": sha256(payload).hexdigest(),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    status = client.get("/api/knowledge/status")

    assert status.status_code == 200
    assert status.json()["ocr_pack"] == {
        "available": True,
        "mode": "local",
        "error_code": None,
        "version": "1.0.0",
    }


def test_duplicate_collection_name_returns_stable_conflict(api) -> None:
    client, _service, _coordinator, _root = api
    create_collection(client)

    response = client.post(
        "/api/knowledge/collections",
        json={"name": "高数", "description": "重复", "color": "#c98f65"},
    )

    assert_error(response, 409, "KNOWLEDGE_COLLECTION_CONFLICT")


def test_collection_detail_returns_counts(api) -> None:
    client, _service, _coordinator, _root = api
    collection = create_collection(client)

    response = client.get(f"/api/knowledge/collections/{collection['id']}")

    assert response.status_code == 200
    assert response.json()["id"] == collection["id"]
    assert response.json()["document_count"] == 0


def test_document_detail_returns_safe_metadata(api) -> None:
    client, service, _coordinator, _root = api
    document = service.repository.upsert_document(
        sha256="d" * 64,
        display_name="极限讲义.pdf",
        extension=".pdf",
        mime_type="application/pdf",
        byte_size=128,
        object_relpath="objects/" + "d" * 64,
    )

    response = client.get(f"/api/knowledge/documents/{document.id}")

    assert response.status_code == 200
    assert response.json()["display_name"] == "极限讲义.pdf"
    assert "object_relpath" not in response.json()


def test_import_accepts_manifest_but_never_an_arbitrary_path(api) -> None:
    client, _service, coordinator, root = api
    collection = create_collection(client)
    manifest = write_object(root, "牛顿第二定律")

    response = client.post(
        "/api/knowledge/imports",
        json={"collection_id": collection["id"], "files": [manifest]},
    )
    rejected = client.post(
        "/api/knowledge/imports",
        json={
            "collection_id": collection["id"],
            "files": [{**manifest, "path": r"C:\secret.txt"}],
        },
    )

    assert response.status_code == 202
    assert len(response.json()["jobs"]) == 1
    assert coordinator.enqueued == [response.json()["jobs"][0]["id"]]
    assert_error(rejected, 422, "REQUEST_VALIDATION_ERROR")
    assert "secret.txt" not in rejected.text


def test_import_route_schedules_real_coordinator_on_app_event_loop(
    api,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, service, _coordinator, root = api
    collection = create_collection(client)
    manifest = write_object(root, "事件循环调度")
    coordinator = KnowledgeImportCoordinator(root)
    started: list[int] = []
    started_event = threading.Event()

    async def record_run(job_id: int) -> None:
        started.append(job_id)
        started_event.set()

    monkeypatch.setattr(coordinator, "_run", record_run)
    service.coordinator = coordinator

    response = client.post(
        "/api/knowledge/imports",
        json={"collection_id": collection["id"], "files": [manifest]},
    )

    assert response.status_code == 202
    assert started_event.wait(timeout=1)
    assert started == [response.json()["jobs"][0]["id"]]


def test_rebuild_route_schedules_real_coordinator_on_app_event_loop(
    api,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, service, _coordinator, root = api
    document = service.repository.upsert_document(
        sha256="e" * 64,
        display_name="重建讲义.txt",
        extension=".txt",
        mime_type="text/plain",
        byte_size=32,
        object_relpath="objects/" + "e" * 64,
    )
    coordinator = KnowledgeImportCoordinator(root)
    started: list[int] = []
    started_event = threading.Event()

    async def record_run(job_id: int) -> None:
        started.append(job_id)
        started_event.set()

    monkeypatch.setattr(coordinator, "_run", record_run)
    service.coordinator = coordinator

    response = client.post(f"/api/knowledge/documents/{document.id}/rebuild")

    assert response.status_code == 202
    assert started_event.wait(timeout=1)
    assert started == [response.json()["id"]]


def test_import_rehashes_object_and_rejects_tampering(api) -> None:
    client, _service, coordinator, root = api
    collection = create_collection(client)
    manifest = write_object(root, "原内容")
    (root / manifest["object_relpath"]).write_text("被篡改", encoding="utf-8")

    response = client.post(
        "/api/knowledge/imports",
        json={"collection_id": collection["id"], "files": [manifest]},
    )

    assert_error(response, 422, "KNOWLEDGE_FILE_SIGNATURE_MISMATCH")
    assert coordinator.enqueued == []


def test_import_batch_rolls_back_all_metadata_when_a_later_object_is_invalid(api) -> None:
    client, service, coordinator, root = api
    collection = create_collection(client)
    first = write_object(root, "第一份资料")
    second = write_object(root, "第二份资料")
    (root / second["object_relpath"]).write_text("已被篡改", encoding="utf-8")

    response = client.post(
        "/api/knowledge/imports",
        json={"collection_id": collection["id"], "files": [first, second]},
    )

    assert_error(response, 422, "KNOWLEDGE_FILE_SIGNATURE_MISMATCH")
    assert service.repository.list_documents() == []
    assert service.repository.list_jobs() == []
    assert coordinator.enqueued == []


def test_import_preparation_uses_a_fresh_database_session(api) -> None:
    client, service, _coordinator, root = api
    collection = create_collection(client)
    manifest = write_object(root, "独立会话")
    opened: list[Session] = []

    def session_factory() -> Session:
        session = Session(service.repository.db.get_bind())
        opened.append(session)
        return session

    service.session_factory = session_factory

    response = client.post(
        "/api/knowledge/imports",
        json={"collection_id": collection["id"], "files": [manifest]},
    )

    assert response.status_code == 202
    assert len(opened) == 1
    assert opened[0] is not service.repository.db


def test_knowledge_search_rejects_body_larger_than_64_kib(api) -> None:
    client, _service, _coordinator, _root = api

    response = client.post(
        "/api/knowledge/search",
        json={"session_id": "student_a", "query": "敏感正文" * 12_000, "limit": 8},
    )

    assert_error(response, 413, "REQUEST_BODY_TOO_LARGE")
    assert "敏感正文" not in response.text


def test_delete_document_cancels_active_import_before_removing_metadata(api) -> None:
    client, service, coordinator, root = api
    manifest = write_object(root, "活动任务")
    document = service.repository.upsert_document(**manifest)
    job = service.repository.create_job(document.id)
    job_id = job.id

    response = client.delete(f"/api/knowledge/documents/{document.id}")

    assert response.status_code == 204
    assert coordinator.cancelled == [job_id]
    assert service.repository.list_documents() == []


def test_delete_document_removes_fts_rows(api) -> None:
    client, service, _coordinator, _root = api
    collection = service.repository.create_collection("待删除索引")
    document = service.repository.upsert_document(
        sha256="f" * 64,
        display_name="待删除.txt",
        extension=".txt",
        mime_type="text/plain",
        byte_size=16,
        object_relpath="objects/" + "f" * 64,
    )
    service.repository.link_document(collection.id, document.id)
    chunks = chunk_blocks(
        [
            StructuredBlock(
                text="需要清理的索引内容",
                heading_path=("清理",),
                locator_type="paragraph",
                locator_start=1,
                locator_end=1,
            )
        ],
        parser_version="chunk-v1",
    )
    service.repository.replace_chunks(document.id, chunks)
    service.search_repository.replace_document_index(document.id)

    response = client.delete(f"/api/knowledge/documents/{document.id}")
    remaining = service.search_repository.db.execute(
        text("SELECT count(*) FROM knowledge_chunks_fts WHERE document_id = :document_id"),
        {"document_id": document.id},
    ).scalar_one()

    assert response.status_code == 204
    assert remaining == 0


def test_delete_document_still_succeeds_when_fts_is_unavailable(
    api,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, service, _coordinator, _root = api
    document = service.repository.upsert_document(
        sha256="9" * 64,
        display_name="隐私删除.txt",
        extension=".txt",
        mime_type="text/plain",
        byte_size=16,
        object_relpath="objects/" + "9" * 64,
    )

    def unavailable(_self, _document_id: int, **_kwargs) -> None:
        raise KnowledgeUnavailable()

    monkeypatch.setattr(KnowledgeSearchRepository, "delete_document_index", unavailable)

    response = client.delete(f"/api/knowledge/documents/{document.id}")

    assert response.status_code == 204
    assert service.repository.list_documents() == []


def test_document_delete_rolls_back_fts_cleanup_when_metadata_delete_fails(
    api,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _client, service, _coordinator, _root = api
    document = service.repository.upsert_document(
        sha256="7" * 64,
        display_name="回滚索引.txt",
        extension=".txt",
        mime_type="text/plain",
        byte_size=16,
        object_relpath="objects/" + "7" * 64,
    )
    chunks = chunk_blocks(
        [
            StructuredBlock(
                text="删除失败时仍需保留索引",
                heading_path=("回滚",),
                locator_type="paragraph",
                locator_start=1,
                locator_end=1,
            )
        ],
        parser_version="chunk-v1",
    )
    service.repository.replace_chunks(document.id, chunks)
    service.search_repository.replace_document_index(document.id)

    def fail_delete(_self, _document_id: int, **_kwargs) -> bool:
        raise RuntimeError("injected metadata delete failure")

    monkeypatch.setattr(KnowledgeRepository, "delete_document_record", fail_delete)

    with pytest.raises(RuntimeError, match="injected metadata delete failure"):
        service._finalize_document_deletion(document.id, document.object_relpath)

    remaining = service.search_repository.db.execute(
        text("SELECT count(*) FROM knowledge_chunks_fts WHERE document_id = :document_id"),
        {"document_id": document.id},
    ).scalar_one()
    assert remaining == 1


def test_session_binding_limits_search_scope(api) -> None:
    client, service, _coordinator, _root = api
    visible = service.repository.create_collection("可见")
    hidden = service.repository.create_collection("不可见")
    for collection, digest, name in (
        (visible, "a" * 64, "可见讲义.txt"),
        (hidden, "b" * 64, "隐藏讲义.txt"),
    ):
        document = service.repository.upsert_document(
            sha256=digest,
            display_name=name,
            extension=".txt",
            mime_type="text/plain",
            byte_size=16,
            object_relpath=f"objects/{digest}",
        )
        service.repository.link_document(collection.id, document.id)
        chunks = chunk_blocks(
            [
                StructuredBlock(
                    text="唯一短语 牛顿第二定律",
                    heading_path=("物理",),
                    locator_type="paragraph",
                    locator_start=1,
                    locator_end=1,
                )
            ],
            parser_version="chunk-v1",
        )
        service.repository.replace_chunks(document.id, chunks)
        service.search_repository.replace_document_index(document.id)

    binding = client.put(
        "/api/sessions/student_a/knowledge-collections",
        json={"collection_ids": [visible.id], "privacy_mode": "allow_model_context"},
    )
    response = client.post(
        "/api/knowledge/search",
        json={"session_id": "student_a", "query": "唯一短语", "limit": 8},
    )

    assert binding.status_code == 200
    assert response.status_code == 200
    assert [item["document_name"] for item in response.json()["items"]] == ["可见讲义.txt"]
    assert response.json()["items"][0]["locator"]["type"] == "paragraph"


def test_cancel_is_idempotent_for_queued_job(api) -> None:
    client, _service, _coordinator, root = api
    collection = create_collection(client)
    manifest = write_object(root, "待取消")
    imported = client.post(
        "/api/knowledge/imports",
        json={"collection_id": collection["id"], "files": [manifest]},
    ).json()
    job_id = imported["jobs"][0]["id"]

    first = client.delete(f"/api/knowledge/imports/{job_id}")
    second = client.delete(f"/api/knowledge/imports/{job_id}")

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["cancel_requested"] is True
    assert second.json()["cancel_requested"] is True


def test_knowledge_status_does_not_change_main_ready_semantics(api) -> None:
    client, _service, _coordinator, _root = api
    live = client.get("/health/live")
    knowledge = client.get("/api/knowledge/status")

    assert live.status_code == 200
    assert live.json() == {"status": "live"}
    assert knowledge.status_code == 200
