from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.config import KNOWLEDGE_DIR
from backend.demo.fixtures import (
    DEMO_COURSE_ARTIFACT,
    DEMO_DATASET_TITLE,
    DEMO_LICENSE,
    DEMO_PROFILE,
    DEMO_RESOURCE,
    DEMO_SESSION_ID,
    DEMO_TEXTBOOK_TEXT,
)
from backend.knowledge.chunking import chunk_blocks
from backend.knowledge.models import ImportJobStatus, KnowledgeChunk
from backend.knowledge.parsers import StructuredBlock
from backend.knowledge.repository import KnowledgeRepository
from backend.knowledge.search import KnowledgeSearchRepository
from backend.protocols.v2.models import (
    ArtifactStatus,
    ArtifactType,
    BundleStatus,
    ResourceArtifact,
    ResourceBundle,
)
from backend.services import db as repo
from backend.services import learning
from backend.services.content_safety.models import RiskLevel, SafetyAction, SafetyMetadata, SafetyStage
from backend.services.model_runtime import model_runtime_router
from backend.services.resource_db import list_bundles, save_bundle


_COLLECTION_NAME = "内置演示教材（CC0）"


def _ensure_demo_document(db: Session) -> tuple[int, int, int]:
    repository = KnowledgeRepository(db, KNOWLEDGE_DIR)
    collection = next((item for item in repository.list_collections() if item.name == _COLLECTION_NAME), None)
    if collection is None:
        collection = repository.create_collection(
            _COLLECTION_NAME,
            "项目原创 CC0 演示材料，可离线使用。",
            "#5f8f8a",
        )
    encoded = DEMO_TEXTBOOK_TEXT.encode("utf-8")
    digest = sha256(encoded).hexdigest()
    objects_root = Path(KNOWLEDGE_DIR) / "objects"
    objects_root.mkdir(parents=True, exist_ok=True)
    object_path = objects_root / digest
    if not object_path.exists():
        object_path.write_bytes(encoded)
    document = repository.upsert_document(
        sha256=digest,
        display_name=f"{DEMO_DATASET_TITLE}.md",
        extension=".md",
        mime_type="text/markdown",
        byte_size=len(encoded),
        object_relpath=f"objects/{digest}",
    )
    repository.link_document(collection.id, document.id)
    blocks = [
        StructuredBlock(
            text=text,
            heading_path=("一次函数探究课",),
            locator_type="page",
            locator_start=page,
            locator_end=page,
        )
        for page, text in enumerate((
            "一次函数 y=kx+b 中，k 是变化率，b 是初始值。",
            "已知 y=2x+1，代入 x=2 得 y=2×2+1=5，并代回检查。",
            "一次函数图像是直线，k 的正负决定上升或下降。",
        ), 1)
    ]
    repository.replace_chunks(document.id, chunk_blocks(blocks, parser_version="demo-cc0-v1"))
    document.status = ImportJobStatus.COMPLETED.value
    document.page_count = 3
    document.favorite = True
    document.safe_error_code = None
    db.commit()
    search = KnowledgeSearchRepository(db)
    search.ensure_schema()
    search.replace_document_index(document.id)
    repository.replace_session_collections(
        DEMO_SESSION_ID,
        [collection.id],
        privacy_mode="allow_model_context",
    )
    cited_chunk = (
        db.query(KnowledgeChunk)
        .filter_by(document_id=document.id, locator_type="page", locator_start=2, locator_end=2)
        .one()
    )
    return collection.id, document.id, cited_chunk.id


def _seed_session(db: Session) -> None:
    session = repo.get_or_create_session(db, DEMO_SESSION_ID)
    repo.set_state(db, session, repo.SessionState.DIAGNOSING)
    repo.set_state(db, session, repo.SessionState.PROFILE_READY)
    repo.save_profile(db, session, DEMO_PROFILE)
    collection_id, document_id, chunk_id = _ensure_demo_document(db)
    repo.begin_generation(db, session)
    resource = repo.complete_generation(
        db,
        session,
        "一次函数",
        "运行内置离线演示",
        DEMO_RESOURCE,
        session.profile_version,
        knowledge_sources=[{
            "reference_id": "资料1",
            "document_id": document_id,
            "document_name": f"{DEMO_DATASET_TITLE}.md",
            "locator_label": "第 2 页",
            "locator": {"type": "page", "start": 2, "end": 2},
            "chunk_id": chunk_id,
            "retrieval_mode": "keyword",
        }],
        safety_metadata=SafetyMetadata(
            stage=SafetyStage.ARTIFACT,
            decision=SafetyAction.ALLOW,
            risk_level=RiskLevel.LOW,
            checked_at=datetime.now(timezone.utc).isoformat(),
        ),
    )
    answers = [(resource.questions[0].id, "4"), (resource.questions[1].id, "2"), (resource.questions[2].id, "5")]
    for index, (question_id, answer) in enumerate(answers, 1):
        learning.submit_attempt(db, DEMO_SESSION_ID, question_id, answer, 0, f"demo-attempt-{index}")

    artifact = ResourceArtifact(
        artifact_id="demo-course-v1",
        type=ArtifactType.COURSE_EXPLANATION,
        title="一次函数可信讲解",
        status=ArtifactStatus.SUCCEEDED,
        body=DEMO_COURSE_ARTIFACT,
        quality_score=96,
        type_specific_data={
            "answer_review": {
                "agent": "answer-reviewer/v1",
                "status": "PASSED",
                "issues": [],
                "repair_attempted": False,
                "formula_checked": True,
                "substitution_checked": True,
            }
        },
    )
    save_bundle(db, DEMO_SESSION_ID, ResourceBundle(
        bundle_id="demo-bundle-v1",
        topic="一次函数",
        profile_version=session.profile_version,
        learning_state_version=str(session.learning_state_version),
        mode="single",
        status=BundleStatus.COMPLETED,
        requested_types=[ArtifactType.COURSE_EXPLANATION],
        artifacts=[artifact],
        aggregate_quality=96,
        created_at="2026-07-18T00:00:00+08:00",
        knowledge_sources=[{
            "reference_id": "资料1",
            "document_id": document_id,
            "document_name": f"{DEMO_DATASET_TITLE}.md",
            "locator_label": "第 2 页",
            "locator": {"type": "page", "start": 2, "end": 2},
            "chunk_id": chunk_id,
            "retrieval_mode": "keyword",
        }],
        evidence_status="grounded",
        knowledge_scope={"document_id": document_id, "page_start": 1, "page_end": 3, "search_mode": "focused"},
    ))
    db.commit()
    repo.append_message(db, DEMO_SESSION_ID, "user", "请用内置原创教材演示一次函数学习闭环。")
    repo.append_message(db, DEMO_SESSION_ID, "assistant", json.dumps({"protocol_version": "learning-resource-bundle/v2", "bundle_id": "demo-bundle-v1"}, ensure_ascii=False))


def _valid_seed(db: Session) -> bool:
    session = repo.get_session(db, DEMO_SESSION_ID)
    return bool(session and len(session.resources) == 1 and len(list_bundles(db, DEMO_SESSION_ID)) == 1)


def demo_snapshot(db: Session) -> dict[str, object]:
    progress = learning.progress_snapshot(db, DEMO_SESSION_ID) or {"knowledge_points": []}
    after = [
        {"name": item["name"], "score": item["mastery_score"]}
        for item in progress["knowledge_points"]
    ]
    online = model_runtime_router.is_ready
    session = repo.get_session(db, DEMO_SESSION_ID)
    collection_ids = KnowledgeRepository(db).bound_collection_ids(DEMO_SESSION_ID) if session else []
    return {
        "session_id": DEMO_SESSION_ID,
        "seeded": session is not None,
        "mode": "online_assisted" if online else "offline",
        "degradation_message": "" if online else "模型不可用：当前展示使用内置原创数据和确定性复核结果，不会伪装成在线生成。",
        "dataset": {
            "title": DEMO_DATASET_TITLE,
            "license": DEMO_LICENSE,
            "original": True,
            "collection_id": collection_ids[0] if collection_ids else None,
        },
        "agent_steps": [
            {"agent": "演示编排 Agent", "status": "COMPLETED", "detail": "加载隔离演示空间"},
            {"agent": "画像 Agent", "status": "COMPLETED", "detail": "载入基础学习画像"},
            {"agent": "检索 Agent", "status": "COMPLETED", "detail": "命中 CC0 原创教材第 2 页"},
            {"agent": "资源 Agent", "status": "COMPLETED", "detail": "生成教材/模型补充分区讲解"},
            {"agent": "答案复核 Agent", "status": "COMPLETED", "detail": "公式、代入和结果检查通过"},
        ],
        "mastery_before": [{"name": "一次函数", "score": 0.25}],
        "mastery_after": after,
        "routes": {"overview": "/dashboard", "agents": "/agents", "tutor": "/tutor"},
    }


def seed_demo(db: Session) -> dict[str, object]:
    if not _valid_seed(db):
        repo.delete_session(db, DEMO_SESSION_ID)
        _seed_session(db)
    return demo_snapshot(db)


def reset_demo(db: Session) -> dict[str, object]:
    repo.delete_session(db, DEMO_SESSION_ID)
    _seed_session(db)
    return demo_snapshot(db)
