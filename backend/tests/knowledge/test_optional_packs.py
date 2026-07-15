from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

import pytest

from backend.knowledge import optional_packs
from backend.knowledge.optional_packs import (
    APP_VERSION,
    CapabilityRegistry,
    OptionalPackInvalid,
    verify_pack,
)


def _manifest(*, digest: str, license_spdx: str = "Apache-2.0") -> dict[str, object]:
    major, minor, _patch = APP_VERSION.split(".")
    return {
        "kind": "ocr",
        "version": "1.0.0",
        "a3_compatibility": f">={major}.{minor},<{major}.{int(minor) + 1}",
        "license_spdx": license_spdx,
        "files": [{"path": "model.bin", "sha256": digest}],
    }


def test_pack_requires_license_hash_and_compatible_version(tmp_path: Path) -> None:
    root = tmp_path / "ocr"
    root.mkdir()
    (root / "model.bin").write_bytes(b"model")

    with pytest.raises(OptionalPackInvalid) as missing_license:
        verify_pack(root, _manifest(digest=sha256(b"model").hexdigest(), license_spdx=""))
    assert missing_license.value.code == "KNOWLEDGE_PACK_MANIFEST_INVALID"

    incompatible = _manifest(digest=sha256(b"model").hexdigest())
    incompatible["a3_compatibility"] = ">=99.0,<100.0"
    with pytest.raises(OptionalPackInvalid) as incompatible_error:
        verify_pack(root, incompatible)
    assert incompatible_error.value.code == "KNOWLEDGE_PACK_INCOMPATIBLE"


def test_pack_rejects_paths_outside_its_root(tmp_path: Path) -> None:
    root = tmp_path / "ocr"
    root.mkdir()
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"outside")
    manifest = _manifest(digest=sha256(b"outside").hexdigest())
    manifest["files"] = [{"path": "../outside.bin", "sha256": sha256(b"outside").hexdigest()}]

    with pytest.raises(OptionalPackInvalid) as exc_info:
        verify_pack(root, manifest)
    assert exc_info.value.code == "KNOWLEDGE_PACK_MANIFEST_INVALID"


def test_pack_reports_missing_model_file_with_stable_code(tmp_path: Path) -> None:
    root = tmp_path / "ocr"
    root.mkdir()

    with pytest.raises(OptionalPackInvalid) as exc_info:
        verify_pack(root, _manifest(digest="0" * 64))

    assert exc_info.value.code == "KNOWLEDGE_PACK_FILE_MISSING"


def test_invalid_model_hash_disables_pack_without_breaking_fts(tmp_path: Path) -> None:
    root = tmp_path / "ocr"
    root.mkdir()
    (root / "model.bin").write_bytes(b"tampered")
    (root / "manifest.json").write_text(
        json.dumps(_manifest(digest="0" * 64)),
        encoding="utf-8",
    )
    registry = CapabilityRegistry()

    registry.load_pack(root)

    assert registry.ocr.available is False
    assert registry.ocr.error_code == "KNOWLEDGE_PACK_HASH_MISMATCH"
    assert registry.fts.available is True


def test_valid_pack_reports_safe_capability_metadata(tmp_path: Path) -> None:
    root = tmp_path / "ocr"
    root.mkdir()
    payload = b"verified-model"
    (root / "model.bin").write_bytes(payload)
    (root / "manifest.json").write_text(
        json.dumps(_manifest(digest=sha256(payload).hexdigest())),
        encoding="utf-8",
    )
    registry = CapabilityRegistry()

    verified = registry.load_pack(root)

    assert verified is not None
    assert registry.ocr.available is True
    assert registry.ocr.mode == "local"
    assert registry.ocr.version == "1.0.0"
    assert str(root) not in repr(registry.ocr)


def test_unchanged_pack_is_not_rehashed_on_each_status_refresh(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "ocr"
    root.mkdir()
    payload = b"stable-model"
    (root / "model.bin").write_bytes(payload)
    (root / "manifest.json").write_text(
        json.dumps(_manifest(digest=sha256(payload).hexdigest())),
        encoding="utf-8",
    )
    calls = 0
    original = optional_packs.stream_sha256

    def counted(path: Path) -> str:
        nonlocal calls
        calls += 1
        return original(path)

    monkeypatch.setattr(optional_packs, "stream_sha256", counted)

    assert CapabilityRegistry().load_pack(root) is not None
    assert CapabilityRegistry().load_pack(root) is not None
    assert calls == 1


def test_verification_cache_is_scoped_to_application_version(tmp_path: Path) -> None:
    root = tmp_path / "ocr"
    root.mkdir()
    payload = b"versioned-model"
    (root / "model.bin").write_bytes(payload)
    (root / "manifest.json").write_text(
        json.dumps(_manifest(digest=sha256(payload).hexdigest())),
        encoding="utf-8",
    )

    compatible = CapabilityRegistry()
    incompatible = CapabilityRegistry(app_version="99.0.0")

    assert compatible.load_pack(root) is not None
    assert incompatible.load_pack(root) is None
    assert incompatible.ocr.error_code == "KNOWLEDGE_PACK_INCOMPATIBLE"
