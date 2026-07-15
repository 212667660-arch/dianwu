from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from threading import RLock
from uuid import uuid4

import numpy as np


_GENERATION_PATTERN = re.compile(r"^[a-f0-9]{32}$")
_MODEL_VERSION_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


class SemanticIndexInvalid(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class OpenedSemanticIndex:
    generation: str
    model_version: str
    chunk_ids: np.ndarray
    vectors: np.ndarray


def _stream_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def reciprocal_rank_fusion(
    rankings: list[list[int]],
    *,
    k: int = 60,
) -> list[int]:
    scores: dict[int, float] = {}
    positions: dict[int, list[int]] = {}
    for ranking_index, ranking in enumerate(rankings):
        seen: set[int] = set()
        for rank, raw_chunk_id in enumerate(ranking, 1):
            chunk_id = int(raw_chunk_id)
            if chunk_id in seen:
                continue
            seen.add(chunk_id)
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank)
            positions.setdefault(chunk_id, [10**9] * len(rankings))[ranking_index] = rank
    return sorted(
        scores,
        key=lambda chunk_id: (
            -scores[chunk_id],
            *positions[chunk_id],
            chunk_id,
        ),
    )


class SemanticIndex:
    def __init__(self, root: Path):
        self.root = Path(root)
        self._lock = RLock()
        self._opened: OpenedSemanticIndex | None = None

    def publish(
        self,
        chunk_ids: np.ndarray,
        vectors: np.ndarray,
        model_version: str,
    ) -> None:
        ids = np.asarray(chunk_ids, dtype=np.int64)
        matrix = np.asarray(vectors, dtype=np.float32)
        if (
            matrix.ndim != 2
            or matrix.shape[0] < 1
            or matrix.shape[1] < 1
            or ids.shape != (matrix.shape[0],)
            or np.any(ids < 1)
            or len(np.unique(ids)) != len(ids)
        ):
            raise SemanticIndexInvalid("KNOWLEDGE_VECTOR_SHAPE_INVALID")
        if not np.isfinite(matrix).all():
            raise SemanticIndexInvalid("KNOWLEDGE_VECTOR_VALUE_INVALID")
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        if np.any(norms <= np.finfo(np.float32).eps):
            raise SemanticIndexInvalid("KNOWLEDGE_VECTOR_VALUE_INVALID")
        if _MODEL_VERSION_PATTERN.fullmatch(str(model_version)) is None:
            raise SemanticIndexInvalid("KNOWLEDGE_VECTOR_MODEL_INVALID")
        normalized = np.ascontiguousarray(matrix / norms, dtype=np.float32)
        generation = uuid4().hex
        self.root.mkdir(parents=True, exist_ok=True)
        versions = self.root / "versions"
        versions.mkdir(exist_ok=True)
        staging = self.root / (".staging-" + generation)
        staging.mkdir()
        try:
            np.save(staging / "chunk_ids.npy", ids, allow_pickle=False)
            np.save(staging / "vectors.npy", normalized, allow_pickle=False)
            manifest = {
                "schema_version": "semantic-index/v1",
                "generation": generation,
                "model_version": str(model_version),
                "dimensions": int(normalized.shape[1]),
                "count": int(normalized.shape[0]),
                "files": {
                    "chunk_ids.npy": _stream_sha256(staging / "chunk_ids.npy"),
                    "vectors.npy": _stream_sha256(staging / "vectors.npy"),
                },
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            (staging / "manifest.json").write_text(
                json.dumps(manifest, ensure_ascii=True, separators=(",", ":")),
                encoding="utf-8",
            )
            target = versions / generation
            os.replace(staging, target)
            pointer_temp = self.root / (".current-" + generation + ".json")
            pointer_temp.write_text(
                json.dumps({"generation": generation}, separators=(",", ":")),
                encoding="utf-8",
            )
            os.replace(pointer_temp, self.root / "current.json")
            with self._lock:
                self._opened = None
        finally:
            if staging.exists():
                for candidate in staging.iterdir():
                    candidate.unlink(missing_ok=True)
                staging.rmdir()

    def _current_generation(self) -> str:
        try:
            raw = json.loads((self.root / "current.json").read_text(encoding="utf-8"))
            generation = str(raw["generation"])
        except Exception as exc:
            raise SemanticIndexInvalid("KNOWLEDGE_VECTOR_INDEX_CORRUPT") from exc
        if _GENERATION_PATTERN.fullmatch(generation) is None:
            raise SemanticIndexInvalid("KNOWLEDGE_VECTOR_INDEX_CORRUPT")
        return generation

    def _quarantine(self, generation: str) -> None:
        with self._lock:
            self._opened = None
        source = self.root / "versions" / generation
        quarantine = self.root / "quarantine"
        quarantine.mkdir(parents=True, exist_ok=True)
        if source.exists():
            target = quarantine / (
                datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
                + "-"
                + generation
                + "-"
                + uuid4().hex[:8]
            )
            try:
                os.replace(source, target)
            except OSError:
                pass
        pointer = self.root / "current.json"
        try:
            current = json.loads(pointer.read_text(encoding="utf-8"))
            if current.get("generation") == generation:
                pointer.unlink(missing_ok=True)
        except Exception:
            pointer.unlink(missing_ok=True)

    def _open(self) -> OpenedSemanticIndex:
        generation = self._current_generation()
        with self._lock:
            if self._opened is not None and self._opened.generation == generation:
                return self._opened
            directory = self.root / "versions" / generation
            try:
                manifest = json.loads(
                    (directory / "manifest.json").read_text(encoding="utf-8")
                )
                if (
                    manifest.get("schema_version") != "semantic-index/v1"
                    or manifest.get("generation") != generation
                    or not isinstance(manifest.get("model_version"), str)
                    or not isinstance(manifest.get("dimensions"), int)
                    or not isinstance(manifest.get("count"), int)
                    or not isinstance(manifest.get("files"), dict)
                ):
                    raise ValueError("semantic manifest is invalid")
                for name in ("chunk_ids.npy", "vectors.npy"):
                    expected_hash = manifest["files"].get(name)
                    if not isinstance(expected_hash, str) or _stream_sha256(
                        directory / name
                    ) != expected_hash:
                        raise ValueError("semantic file hash mismatch")
                ids = np.load(
                    directory / "chunk_ids.npy",
                    mmap_mode="r",
                    allow_pickle=False,
                )
                matrix = np.load(
                    directory / "vectors.npy",
                    mmap_mode="r",
                    allow_pickle=False,
                )
                if (
                    ids.dtype != np.int64
                    or matrix.dtype != np.float32
                    or ids.shape != (manifest["count"],)
                    or matrix.shape
                    != (manifest["count"], manifest["dimensions"])
                ):
                    raise ValueError("semantic array shape is invalid")
                opened = OpenedSemanticIndex(
                    generation=generation,
                    model_version=manifest["model_version"],
                    chunk_ids=ids,
                    vectors=matrix,
                )
            except Exception as exc:
                self._quarantine(generation)
                raise SemanticIndexInvalid(
                    "KNOWLEDGE_VECTOR_INDEX_CORRUPT"
                ) from exc
            self._opened = opened
            return opened

    def query(
        self,
        vector: np.ndarray,
        limit: int = 30,
        *,
        expected_model_version: str | None = None,
    ) -> list[int]:
        opened = self._open()
        if (
            expected_model_version is not None
            and opened.model_version != expected_model_version
        ):
            raise SemanticIndexInvalid("KNOWLEDGE_VECTOR_MODEL_MISMATCH")
        query = np.asarray(vector, dtype=np.float32)
        if query.shape != (opened.vectors.shape[1],):
            raise SemanticIndexInvalid("KNOWLEDGE_VECTOR_SHAPE_INVALID")
        if not np.isfinite(query).all():
            raise SemanticIndexInvalid("KNOWLEDGE_VECTOR_VALUE_INVALID")
        norm = float(np.linalg.norm(query))
        if norm <= float(np.finfo(np.float32).eps):
            raise SemanticIndexInvalid("KNOWLEDGE_VECTOR_VALUE_INVALID")
        normalized = query / norm
        scores = np.asarray(opened.vectors @ normalized)
        count = max(0, min(int(limit), len(opened.chunk_ids), 30))
        if count == 0:
            return []
        if count == len(opened.chunk_ids):
            candidates = np.arange(count)
        else:
            candidates = np.argpartition(-scores, count - 1)[:count]
        order = candidates[
            np.lexsort(
                (
                    np.asarray(opened.chunk_ids)[candidates],
                    -scores[candidates],
                )
            )
        ]
        return np.asarray(opened.chunk_ids[order], dtype=np.int64).astype(int).tolist()
