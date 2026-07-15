from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from backend.database import Base
from backend.knowledge.chunking import chunk_blocks
from backend.knowledge.parsers import StructuredBlock
from backend.knowledge.repository import KnowledgeRepository
from backend.knowledge.search import KnowledgeSearchRepository


@pytest.fixture()
def search_fixture(tmp_path: Path):
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record) -> None:
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    db = Session(engine)
    repository = KnowledgeRepository(db, tmp_path / "knowledge")
    first = repository.create_collection("集合一")
    second = repository.create_collection("集合二")
    search = KnowledgeSearchRepository(db)
    search.ensure_schema()
    try:
        yield repository, search, first.id, second.id
    finally:
        db.close()
        engine.dispose()


def index_document(
    repository: KnowledgeRepository,
    search: KnowledgeSearchRepository,
    *,
    collection_id: int,
    digest: str,
    display_name: str,
    text: str,
) -> int:
    document = repository.upsert_document(
        sha256=digest,
        display_name=display_name,
        extension=".txt",
        mime_type="text/plain",
        byte_size=len(text.encode("utf-8")),
        object_relpath=f"objects/{digest}",
    )
    repository.link_document(collection_id, document.id)
    chunks = chunk_blocks(
        [
            StructuredBlock(
                text=text,
                heading_path=("物理",),
                locator_type="paragraph",
                locator_start=1,
                locator_end=1,
            )
        ],
        parser_version="chunk-v1",
    )
    repository.replace_chunks(document.id, chunks)
    search.replace_document_index(document.id)
    return chunks[0].ordinal


def test_cjk_query_matches_single_and_bigram_tokens(search_fixture) -> None:
    repository, search, first_id, _second_id = search_fixture
    index_document(
        repository,
        search,
        collection_id=first_id,
        digest="a" * 64,
        display_name="物理讲义.txt",
        text="牛顿第二定律说明力与加速度的关系",
    )

    results = search.search("牛顿 定律", collection_ids=[first_id], limit=30)

    assert len(results) == 1
    assert results[0].document_name == "物理讲义.txt"
    assert "牛顿第二定律" in results[0].text


@pytest.mark.parametrize("query", ['"', "NEAR(", "a OR *", "-"])
def test_query_syntax_is_treated_as_data(search_fixture, query: str) -> None:
    repository, search, first_id, _second_id = search_fixture
    index_document(
        repository,
        search,
        collection_id=first_id,
        digest="b" * 64,
        display_name="安全.txt",
        text="near ordinary learning text",
    )

    assert isinstance(search.search(query, collection_ids=[first_id]), list)


def test_collection_scope_prevents_cross_collection_leak(search_fixture) -> None:
    repository, search, first_id, second_id = search_fixture
    index_document(
        repository,
        search,
        collection_id=first_id,
        digest="c" * 64,
        display_name="可见.txt",
        text="唯一短语 私有资料",
    )
    index_document(
        repository,
        search,
        collection_id=second_id,
        digest="d" * 64,
        display_name="隐藏.txt",
        text="唯一短语 私有资料",
    )

    results = search.search("唯一短语", collection_ids=[first_id])

    assert [item.document_name for item in results] == ["可见.txt"]
