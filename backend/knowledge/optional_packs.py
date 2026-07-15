from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import re
from threading import RLock
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator


APP_VERSION = "0.2.0"
_VERSION_PATTERN = re.compile(r"^(\d+)(?:\.(\d+))?(?:\.(\d+))?$")
_SPECIFIER_PATTERN = re.compile(r"^(>=|<=|==|>|<)(\d+(?:\.\d+){0,2})$")
_VERIFICATION_CACHE: dict[
    str,
    tuple[tuple[object, ...], VerifiedPack | None, str | None, str],
] = {}
_VERIFICATION_CACHE_LOCK = RLock()


class OptionalPackInvalid(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class _StrictPackModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PackFile(_StrictPackModel):
    path: str = Field(min_length=1, max_length=240)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts or "\\" in value:
            raise ValueError("pack file path is unsafe")
        return value


class PackManifest(_StrictPackModel):
    kind: Literal["ocr", "semantic"]
    version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    a3_compatibility: str = Field(min_length=1, max_length=64)
    license_spdx: str = Field(min_length=1, max_length=64)
    files: list[PackFile] = Field(min_length=1, max_length=32)

    @field_validator("license_spdx")
    @classmethod
    def validate_license(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("pack license is missing")
        return normalized


@dataclass(frozen=True)
class VerifiedPack:
    root: Path
    manifest: PackManifest


@dataclass(frozen=True)
class CapabilityState:
    available: bool
    mode: str
    error_code: str | None = None
    version: str | None = None


def stream_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _version_tuple(value: str) -> tuple[int, int, int]:
    matched = _VERSION_PATTERN.fullmatch(value.strip())
    if matched is None:
        raise OptionalPackInvalid("KNOWLEDGE_PACK_MANIFEST_INVALID")
    return tuple(int(item or 0) for item in matched.groups())


def verify_compatibility(specification: str, app_version: str = APP_VERSION) -> None:
    current = _version_tuple(app_version)
    clauses = [item.strip() for item in specification.split(",") if item.strip()]
    if not clauses:
        raise OptionalPackInvalid("KNOWLEDGE_PACK_MANIFEST_INVALID")
    for clause in clauses:
        matched = _SPECIFIER_PATTERN.fullmatch(clause)
        if matched is None:
            raise OptionalPackInvalid("KNOWLEDGE_PACK_MANIFEST_INVALID")
        operator, raw_version = matched.groups()
        expected = _version_tuple(raw_version)
        compatible = {
            ">=": current >= expected,
            "<=": current <= expected,
            "==": current == expected,
            ">": current > expected,
            "<": current < expected,
        }[operator]
        if not compatible:
            raise OptionalPackInvalid("KNOWLEDGE_PACK_INCOMPATIBLE")


def verify_pack(
    root: Path,
    raw_manifest: dict[str, object],
    *,
    app_version: str = APP_VERSION,
) -> VerifiedPack:
    try:
        manifest = PackManifest.model_validate(raw_manifest)
        resolved_root = Path(root).resolve(strict=True)
        if not resolved_root.is_dir():
            raise OptionalPackInvalid("KNOWLEDGE_PACK_MANIFEST_INVALID")
        verify_compatibility(manifest.a3_compatibility, app_version)
        for item in manifest.files:
            candidate = resolved_root / item.path
            if not candidate.exists():
                raise OptionalPackInvalid("KNOWLEDGE_PACK_FILE_MISSING")
            candidate = candidate.resolve(strict=True)
            candidate.relative_to(resolved_root)
            if not candidate.is_file():
                raise OptionalPackInvalid("KNOWLEDGE_PACK_FILE_MISSING")
            if stream_sha256(candidate) != item.sha256:
                raise OptionalPackInvalid("KNOWLEDGE_PACK_HASH_MISMATCH")
    except OptionalPackInvalid:
        raise
    except (OSError, ValueError, ValidationError) as exc:
        raise OptionalPackInvalid("KNOWLEDGE_PACK_MANIFEST_INVALID") from exc
    return VerifiedPack(root=resolved_root, manifest=manifest)


class CapabilityRegistry:
    def __init__(self, *, app_version: str = APP_VERSION) -> None:
        self.app_version = app_version
        self.fts = CapabilityState(True, "keyword")
        self.ocr = CapabilityState(
            False,
            "optional",
            "KNOWLEDGE_OCR_PACK_REQUIRED",
        )
        self.semantic = CapabilityState(False, "optional")

    def _set_unavailable(self, kind: str, code: str) -> None:
        state = CapabilityState(False, "optional", code)
        if kind == "semantic":
            self.semantic = state
        else:
            self.ocr = state

    def load_pack(self, root: Path) -> VerifiedPack | None:
        pack_root = Path(root)
        kind = "semantic" if pack_root.name.lower() == "semantic" else "ocr"
        try:
            manifest_text = (pack_root / "manifest.json").read_text(encoding="utf-8")
            raw = json.loads(manifest_text)
            if isinstance(raw, dict) and raw.get("kind") in {"ocr", "semantic"}:
                kind = str(raw["kind"])
            if not isinstance(raw, dict):
                raise OptionalPackInvalid("KNOWLEDGE_PACK_MANIFEST_INVALID")
            cache_key = f"{pack_root.resolve(strict=True)}\0{self.app_version}"
            fingerprint_parts: list[object] = [
                sha256(manifest_text.encode("utf-8")).hexdigest()
            ]
            for item in raw.get("files", []):
                if not isinstance(item, dict) or not isinstance(item.get("path"), str):
                    continue
                relative = PurePosixPath(item["path"])
                if relative.is_absolute() or ".." in relative.parts or "\\" in item["path"]:
                    continue
                candidate = pack_root / item["path"]
                try:
                    stat = candidate.stat()
                    fingerprint_parts.append(
                        (item["path"], stat.st_size, stat.st_mtime_ns)
                    )
                except OSError:
                    fingerprint_parts.append((item["path"], None, None))
            fingerprint = tuple(fingerprint_parts)
            with _VERIFICATION_CACHE_LOCK:
                cached = _VERIFICATION_CACHE.get(cache_key)
                if cached is not None and cached[0] == fingerprint:
                    _fingerprint, verified, error_code, cached_kind = cached
                    if verified is None:
                        self._set_unavailable(cached_kind, str(error_code))
                        return None
                else:
                    try:
                        verified = verify_pack(
                            pack_root,
                            raw,
                            app_version=self.app_version,
                        )
                    except OptionalPackInvalid as exc:
                        _VERIFICATION_CACHE[cache_key] = (
                            fingerprint,
                            None,
                            exc.code,
                            kind,
                        )
                        raise
                    _VERIFICATION_CACHE[cache_key] = (
                        fingerprint,
                        verified,
                        None,
                        verified.manifest.kind,
                    )
        except OptionalPackInvalid as exc:
            self._set_unavailable(kind, exc.code)
            return None
        except (OSError, UnicodeError, json.JSONDecodeError):
            self._set_unavailable(kind, "KNOWLEDGE_PACK_MANIFEST_INVALID")
            return None
        state = CapabilityState(
            True,
            "local",
            None,
            verified.manifest.version,
        )
        if verified.manifest.kind == "semantic":
            self.semantic = state
        else:
            self.ocr = state
        return verified
