from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Iterable

from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from backend.knowledge.chunking import cjk_search_tokens
from backend.knowledge.models import KnowledgeChunk, KnowledgeDocument


logger = logging.getLogger(__name__)
FTS_TABLE = "knowledge_chunks_fts"
_fts_available: bool | None = None


class KnowledgeUnavailable(RuntimeError):
    def __init__(self, code: str = "KNOWLEDGE_INDEX_UNAVAILABLE"):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class SearchHit:
    chunk_id: int
    document_id: int
    document_name: str
    text: str
    heading_path: str
    locator_type: str
    locator_start: int
    locator_end: int
    sheet_name: str | None
    score: float
    retrieval_mode: str = "keyword"
    parser_version: str = "chunk-v1"
    index_version: str = "fts-v1"


_CREATE_FTS = """
CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_chunks_fts USING fts5(
    chunk_id UNINDEXED,
    document_id UNINDEXED,
    display_name,
    heading,
    content,
    search_tokens,
    tokenize='unicode61 remove_diacritics 2'
)
"""


def initialize_knowledge_fts(engine: Engine) -> bool:
    global _fts_available
    try:
        with engine.begin() as connection:
            if engine.dialect.name != "sqlite":
                raise KnowledgeUnavailable()
            enabled = connection.execute(
                text("SELECT sqlite_compileoption_used('ENABLE_FTS5')")
            ).scalar_one()
            if int(enabled) != 1:
                raise KnowledgeUnavailable()
            connection.execute(text(_CREATE_FTS))
        _fts_available = True
    except Exception:
        logger.warning("knowledge capability unavailable: KNOWLEDGE_INDEX_UNAVAILABLE")
        _fts_available = False
    return _fts_available


def knowledge_fts_available() -> bool:
    return _fts_available is True


class KnowledgeSearchRepository:
    def __init__(self, db: Session):
        self.db = db

    def ensure_schema(self) -> None:
        bind = self.db.get_bind()
        if bind.dialect.name != "sqlite":
            raise KnowledgeUnavailable()
        enabled = self.db.execute(
            text("SELECT sqlite_compileoption_used('ENABLE_FTS5')")
        ).scalar_one()
        if int(enabled) != 1:
            raise KnowledgeUnavailable()
        self.db.execute(text(_CREATE_FTS))
        self.db.commit()

    def replace_document_index(self, document_id: int) -> None:
        self.ensure_schema()
        document = self.db.get(KnowledgeDocument, document_id)
        if document is None:
            raise LookupError("knowledge document was not found")
        self.db.execute(
            text("DELETE FROM knowledge_chunks_fts WHERE document_id = :document_id"),
            {"document_id": document_id},
        )
        chunks = (
            self.db.query(KnowledgeChunk)
            .filter(KnowledgeChunk.document_id == document_id)
            .order_by(KnowledgeChunk.ordinal)
            .all()
        )
        for chunk in chunks:
            tokens = cjk_search_tokens(
                " ".join((document.display_name, chunk.heading_path, chunk.text))
            )
            self.db.execute(
                text(
                    """
                    INSERT INTO knowledge_chunks_fts(
                        chunk_id, document_id, display_name, heading, content, search_tokens
                    ) VALUES (
                        :chunk_id, :document_id, :display_name, :heading, :content, :search_tokens
                    )
                    """
                ),
                {
                    "chunk_id": chunk.id,
                    "document_id": document_id,
                    "display_name": document.display_name,
                    "heading": chunk.heading_path,
                    "content": chunk.text,
                    "search_tokens": tokens,
                },
            )
        self.db.commit()

    def delete_document_index(self, document_id: int, *, commit: bool = True) -> None:
        self.ensure_schema()
        self.db.execute(
            text("DELETE FROM knowledge_chunks_fts WHERE document_id = :document_id"),
            {"document_id": document_id},
        )
        if commit:
            self.db.commit()

    def search(
        self,
        query: str,
        collection_ids: Iterable[int],
        limit: int = 30,
    ) -> list[SearchHit]:
        selected_collections = sorted(
            {
                int(collection_id)
                for collection_id in collection_ids
                if isinstance(collection_id, int) and collection_id > 0
            }
        )
        if not selected_collections:
            return []
        tokens = cjk_search_tokens(query).split()
        if not tokens:
            return []
        bounded_limit = max(1, min(int(limit), 30))
        match = " AND ".join(
            '"' + token.replace('"', '""') + '"'
            for token in tokens[:64]
        )
        placeholders = ", ".join(
            ":collection_" + str(index)
            for index in range(len(selected_collections))
        )
        parameters = {
            "match": match,
            "limit": bounded_limit,
            **{
                "collection_" + str(index): collection_id
                for index, collection_id in enumerate(selected_collections)
            },
        }
        rows = self.db.execute(
            text(
                """
                SELECT
                    chunk.id AS chunk_id,
                    document.id AS document_id,
                    document.display_name AS document_name,
                    chunk.text AS content,
                    chunk.heading_path AS heading_path,
                    chunk.locator_type AS locator_type,
                    chunk.locator_start AS locator_start,
                    chunk.locator_end AS locator_end,
                    chunk.sheet_name AS sheet_name,
                    chunk.parser_version AS parser_version,
                    bm25(knowledge_chunks_fts) AS rank
                FROM knowledge_chunks_fts
                JOIN knowledge_chunks AS chunk
                    ON chunk.id = CAST(knowledge_chunks_fts.chunk_id AS INTEGER)
                JOIN knowledge_documents AS document
                    ON document.id = chunk.document_id
                WHERE knowledge_chunks_fts MATCH :match
                  AND EXISTS (
                    SELECT 1
                    FROM knowledge_collection_documents AS link
                    WHERE link.document_id = document.id
                      AND link.collection_id IN (""" + placeholders + """)
                  )
                ORDER BY rank ASC, chunk.id ASC
                LIMIT :limit
                """
            ),
            parameters,
        ).mappings()
        return [
            SearchHit(
                chunk_id=int(row["chunk_id"]),
                document_id=int(row["document_id"]),
                document_name=str(row["document_name"]),
                text=str(row["content"]),
                heading_path=str(row["heading_path"] or ""),
                locator_type=str(row["locator_type"]),
                locator_start=int(row["locator_start"]),
                locator_end=int(row["locator_end"]),
                sheet_name=row["sheet_name"],
                score=-float(row["rank"]),
                parser_version=str(row["parser_version"]),
                index_version="fts-v1",
            )
            for row in rows
        ]
