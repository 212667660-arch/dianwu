from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from backend.config import DATA_DIR, settings

connect_args = {"check_same_thread": False} if settings.resolved_database_url.startswith("sqlite") else {}
engine = create_engine(settings.resolved_database_url, connect_args=connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _add_missing_columns(table_name: str, additions: dict[str, str]) -> None:
    inspector = inspect(engine)
    if table_name not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns(table_name)}
    with engine.begin() as connection:
        for name, definition in additions.items():
            if name not in columns:
                connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {name} {definition}"))


def _sqlite_migrate() -> None:
    if not settings.resolved_database_url.startswith("sqlite"):
        return
    _add_missing_columns("chat_sessions", {
        "state": "VARCHAR(32) NOT NULL DEFAULT 'NEW'",
        "diagnosis_turns": "INTEGER NOT NULL DEFAULT 0",
        "profile_version": "INTEGER NOT NULL DEFAULT 0",
        "learning_state_version": "INTEGER NOT NULL DEFAULT 0",
        "last_stable_state": "VARCHAR(32) NOT NULL DEFAULT 'NEW'",
        "last_error_code": "VARCHAR(64)",
    })
    _add_missing_columns("resources", {
        "request_message": "TEXT NOT NULL DEFAULT ''",
        "sources_json": "TEXT NOT NULL DEFAULT '[]'",
        "knowledge_sources_json": "TEXT NOT NULL DEFAULT '[]'",
        "profile_version": "INTEGER NOT NULL DEFAULT 0",
        "learning_state_version": "INTEGER NOT NULL DEFAULT 0",
        "protocol_version": "VARCHAR(32) NOT NULL DEFAULT 'learning-resource/v1'",
        "status": "VARCHAR(32) NOT NULL DEFAULT 'COMPLETED'",
        "error_code": "VARCHAR(64)",
        "quality_score": "INTEGER NOT NULL DEFAULT 0",
        "quality_issues_json": "TEXT NOT NULL DEFAULT '[]'",
    })
    with engine.begin() as connection:
        connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_messages_session_seq ON messages(session_id, seq)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_resources_cache_lookup ON resources(session_id, profile_version, request_message, created_at)"))
    with engine.begin() as connection:
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS resource_bundles (
                bundle_id VARCHAR(64) PRIMARY KEY,
                session_id VARCHAR(64) NOT NULL DEFAULT '',
                protocol_version VARCHAR(64) NOT NULL DEFAULT 'learning-resource-bundle/v2',
                topic VARCHAR(200) NOT NULL DEFAULT '',
                profile_version INTEGER NOT NULL DEFAULT 1,
                learning_state_version VARCHAR(128) NOT NULL DEFAULT 'v1',
                mode VARCHAR(16) NOT NULL DEFAULT 'bundle',
                status VARCHAR(32) NOT NULL DEFAULT 'FAILED',
                requested_types TEXT NOT NULL DEFAULT '[]',
                artifacts_json TEXT NOT NULL DEFAULT '[]',
                aggregate_quality REAL NOT NULL DEFAULT 0.0,
                created_at VARCHAR(64) NOT NULL DEFAULT '',
                knowledge_sources_json TEXT NOT NULL DEFAULT '[]',
                public_sources_json TEXT NOT NULL DEFAULT '[]'
            )
        """))
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS resource_artifacts (
                artifact_id VARCHAR(64) PRIMARY KEY,
                bundle_id VARCHAR(64) NOT NULL DEFAULT '',
                type VARCHAR(32) NOT NULL DEFAULT '',
                title VARCHAR(300) NOT NULL DEFAULT '',
                status VARCHAR(16) NOT NULL DEFAULT 'FAILED',
                body TEXT NOT NULL DEFAULT '',
                type_specific_data_json TEXT NOT NULL DEFAULT '{}',
                quality_score INTEGER NOT NULL DEFAULT 0,
                quality_issues_json TEXT NOT NULL DEFAULT '[]',
                error_code VARCHAR(100),
                retryable INTEGER NOT NULL DEFAULT 0
            )
        """))
        connection.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_artifacts_bundle_id ON resource_artifacts(bundle_id)"
        ))
        connection.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_resource_bundles_session_created "
            "ON resource_bundles(session_id, created_at)"
        ))


def init_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    from backend.services import db as _models  # noqa: F401
    from backend.knowledge import models as _knowledge_models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _sqlite_migrate()
    from backend.knowledge.search import initialize_knowledge_fts

    initialize_knowledge_fts(engine)
    db = SessionLocal()
    try:
        _models.backfill_learning_state(db)
    finally:
        db.close()
