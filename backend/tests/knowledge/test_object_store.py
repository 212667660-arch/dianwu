from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
from pathlib import Path

import pytest

from backend.knowledge.object_store import KnowledgeObjectStore, UnsafeKnowledgeObjectPath


def test_object_store_rejects_traversal_absolute_paths_and_symlinks(tmp_path: Path) -> None:
    store = KnowledgeObjectStore(tmp_path / "knowledge")
    store.objects_root.mkdir(parents=True)
    outside = tmp_path / "secret.txt"
    outside.write_text("secret", encoding="utf-8")
    link = store.objects_root / ("a" * 64)
    try:
        link.symlink_to(outside)
    except OSError:
        link = None

    with pytest.raises(UnsafeKnowledgeObjectPath):
        store.resolve("../secret.txt")
    with pytest.raises(UnsafeKnowledgeObjectPath):
        store.resolve(str(outside.resolve()))
    if link is not None:
        with pytest.raises(UnsafeKnowledgeObjectPath):
            store.resolve(f"objects/{'a' * 64}")


def test_orphan_cleanup_keeps_recent_and_referenced_objects(tmp_path: Path) -> None:
    now = datetime(2026, 7, 15, 12, tzinfo=timezone.utc)
    store = KnowledgeObjectStore(tmp_path / "knowledge", clock=lambda: now)
    store.objects_root.mkdir(parents=True)
    old_orphan = store.objects_root / ("a" * 64)
    recent_orphan = store.objects_root / ("b" * 64)
    referenced = store.objects_root / ("c" * 64)
    invalid_name = store.objects_root / "not-a-hash"
    for path, age in (
        (old_orphan, 25),
        (recent_orphan, 23),
        (referenced, 48),
        (invalid_name, 48),
    ):
        path.write_bytes(b"fixture")
        timestamp = (now - timedelta(hours=age)).timestamp()
        os.utime(path, (timestamp, timestamp))

    removed = store.cleanup_orphans(
        referenced_hashes={"c" * 64},
        minimum_age=timedelta(hours=24),
    )

    assert removed == ["a" * 64]
    assert not old_orphan.exists()
    assert recent_orphan.exists()
    assert referenced.exists()
    assert invalid_name.exists()
