from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session

from backend.database import Base
from backend.knowledge.chunking import chunk_blocks
from backend.knowledge.parsers import StructuredBlock
from backend.knowledge.repository import KnowledgeRepository
from backend.knowledge.search import KnowledgeSearchRepository
from backend.knowledge.semantic import (
    SemanticIndex,
    SemanticIndexInvalid,
    reciprocal_rank_fusion,
)


def test_exact_cosine_returns_highest_normalized_vector(tmp_path: Path) -> None:
    index = SemanticIndex(tmp_path)
    index.publish(
        chunk_ids=np.array([11, 12, 13], dtype=np.int64),
        vectors=np.array(
            [[1.0, 0.0], [0.7, 0.7], [0.0, 1.0]],
            dtype=np.float32,
        ),
        model_version="test-v1",
    )

    assert index.query(np.array([1.0, 0.0], dtype=np.float32), 2) == [11, 12]


@pytest.mark.parametrize(
    ("vector", "code"),
    [
        (np.array([0.0, 0.0], dtype=np.float32), "KNOWLEDGE_VECTOR_VALUE_INVALID"),
        (np.array([np.nan, 0.0], dtype=np.float32), "KNOWLEDGE_VECTOR_VALUE_INVALID"),
        (np.array([1.0, 0.0, 0.0], dtype=np.float32), "KNOWLEDGE_VECTOR_SHAPE_INVALID"),
    ],
)
def test_query_rejects_zero_nonfinite_and_wrong_dimension_vectors(
    tmp_path: Path,
    vector: np.ndarray,
    code: str,
) -> None:
    index = SemanticIndex(tmp_path)
    index.publish(
        np.array([1], dtype=np.int64),
        np.array([[1.0, 0.0]], dtype=np.float32),
        "test-v1",
    )

    with pytest.raises(SemanticIndexInvalid) as exc_info:
        index.query(vector)
    assert exc_info.value.code == code


def test_model_version_mismatch_disables_stale_index(tmp_path: Path) -> None:
    index = SemanticIndex(tmp_path)
    index.publish(
        np.array([1], dtype=np.int64),
        np.array([[1.0, 0.0]], dtype=np.float32),
        "model-v1",
    )

    with pytest.raises(SemanticIndexInvalid) as exc_info:
        index.query(
            np.array([1.0, 0.0], dtype=np.float32),
            expected_model_version="model-v2",
        )
    assert exc_info.value.code == "KNOWLEDGE_VECTOR_MODEL_MISMATCH"


def test_rrf_merges_and_deduplicates_rankings() -> None:
    assert reciprocal_rank_fusion([[1, 2, 3], [3, 2, 4]], k=60)[:4] == [
        3,
        2,
        1,
        4,
    ]


@pytest.fixture()
def search_fixture(tmp_path: Path):
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record) -> None:
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    db = Session(engine)
    repository = KnowledgeRepository(db, tmp_path / "knowledge")
    collection = repository.create_collection("物理")
    keyword = KnowledgeSearchRepository(db)
    keyword.ensure_schema()
    document = repository.upsert_document(
        sha256="a" * 64,
        display_name="物理讲义.txt",
        extension=".txt",
        mime_type="text/plain",
        byte_size=32,
        object_relpath="objects/" + "a" * 64,
    )
    repository.link_document(collection.id, document.id)
    repository.replace_chunks(
        document.id,
        chunk_blocks(
            [
                StructuredBlock(
                    text="牛顿第二定律说明力与加速度的关系",
                    heading_path=("物理",),
                    locator_type="paragraph",
                    locator_start=1,
                    locator_end=1,
                )
            ],
            parser_version="chunk-v1",
        ),
    )
    keyword.replace_document_index(document.id)
    try:
        yield db, collection.id, tmp_path
    finally:
        db.close()
        engine.dispose()


def test_corrupt_semantic_generation_is_quarantined_and_keyword_search_survives(
    search_fixture,
) -> None:
    db, collection_id, tmp_path = search_fixture
    index = SemanticIndex(tmp_path / "semantic")
    chunk_id = int(db.execute(text("SELECT id FROM knowledge_chunks")).scalar_one())
    index.publish(
        np.array([chunk_id], dtype=np.int64),
        np.array([[1.0, 0.0]], dtype=np.float32),
        "test-v1",
    )
    pointer = json.loads((index.root / "current.json").read_text(encoding="utf-8"))
    generation = index.root / "versions" / pointer["generation"]
    (generation / "manifest.json").write_text("{broken", encoding="utf-8")
    hybrid = KnowledgeSearchRepository(
        db,
        semantic_index=index,
        encode_query=lambda _query: np.array([1.0, 0.0], dtype=np.float32),
        semantic_model_version="test-v1",
    )

    results = hybrid.search("牛顿", [collection_id])

    assert results
    assert results[0].retrieval_mode == "keyword"
    assert any((index.root / "quarantine").iterdir())


def test_hybrid_search_ignores_missing_chunk_ids_and_marks_mode(search_fixture) -> None:
    db, collection_id, tmp_path = search_fixture
    chunk_id = int(db.execute(text("SELECT id FROM knowledge_chunks")).scalar_one())
    index = SemanticIndex(tmp_path / "semantic")
    index.publish(
        np.array([999_999, chunk_id], dtype=np.int64),
        np.array([[1.0, 0.0], [0.8, 0.2]], dtype=np.float32),
        "test-v1",
    )
    hybrid = KnowledgeSearchRepository(
        db,
        semantic_index=index,
        encode_query=lambda _query: np.array([1.0, 0.0], dtype=np.float32),
        semantic_model_version="test-v1",
    )

    results = hybrid.search("牛顿", [collection_id], limit=8)

    assert [item.chunk_id for item in results] == [chunk_id]
    assert results[0].retrieval_mode == "hybrid"
