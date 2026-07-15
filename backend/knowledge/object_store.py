from __future__ import annotations

from collections.abc import Callable, Collection
from datetime import datetime, timedelta, timezone
from pathlib import Path
import re


_OBJECT_RELPATH = re.compile(r"^objects/([a-f0-9]{64})$")
_OBJECT_NAME = re.compile(r"^[a-f0-9]{64}$")


class UnsafeKnowledgeObjectPath(ValueError):
    pass


class KnowledgeObjectStore:
    def __init__(
        self,
        root: Path,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.root = Path(root)
        self.objects_root = self.root / "objects"
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def ensure_directories(self) -> None:
        self.objects_root.mkdir(parents=True, exist_ok=True)

    def resolve(self, object_relpath: str, *, require_exists: bool = True) -> Path:
        matched = _OBJECT_RELPATH.fullmatch(object_relpath)
        if matched is None:
            raise UnsafeKnowledgeObjectPath("knowledge object path is invalid")
        objects_root = self.objects_root.resolve(strict=False)
        candidate = (self.root / object_relpath).resolve(strict=require_exists)
        try:
            candidate.relative_to(objects_root)
        except ValueError as exc:
            raise UnsafeKnowledgeObjectPath("knowledge object escapes object root") from exc
        if require_exists and (not candidate.is_file() or candidate.is_symlink()):
            raise UnsafeKnowledgeObjectPath("knowledge object is not a regular file")
        return candidate

    def cleanup_orphans(
        self,
        *,
        referenced_hashes: Collection[str],
        minimum_age: timedelta = timedelta(hours=24),
    ) -> list[str]:
        self.ensure_directories()
        referenced = set(referenced_hashes)
        cutoff = self._clock().timestamp() - minimum_age.total_seconds()
        removed: list[str] = []
        for candidate in sorted(self.objects_root.iterdir(), key=lambda item: item.name):
            if not _OBJECT_NAME.fullmatch(candidate.name):
                continue
            if candidate.name in referenced:
                continue
            try:
                stat = candidate.lstat()
            except FileNotFoundError:
                continue
            if stat.st_mtime > cutoff:
                continue
            if not candidate.is_file() and not candidate.is_symlink():
                continue
            candidate.unlink(missing_ok=True)
            removed.append(candidate.name)
        return removed

    def delete(self, object_relpath: str) -> None:
        candidate = self.resolve(object_relpath)
        candidate.unlink(missing_ok=True)
