from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.knowledge.schemas import ImportBatchRequest, ImportManifest


def manifest(**overrides) -> dict[str, object]:
    digest = "a" * 64
    value: dict[str, object] = {
        "sha256": digest,
        "display_name": "讲义.pdf",
        "extension": ".pdf",
        "mime_type": "application/pdf",
        "byte_size": 1024,
        "object_relpath": f"objects/{digest}",
    }
    value.update(overrides)
    return value


def test_import_manifest_accepts_only_controlled_object_metadata() -> None:
    value = ImportManifest.model_validate(manifest())
    assert value.display_name == "讲义.pdf"
    assert value.object_relpath == f"objects/{'a' * 64}"

    with pytest.raises(ValidationError):
        ImportManifest.model_validate(manifest(path=r"C:\secret.txt"))
    with pytest.raises(ValidationError):
        ImportManifest.model_validate(manifest(display_name="../secret.txt"))
    with pytest.raises(ValidationError):
        ImportManifest.model_validate(manifest(object_relpath="../secret.txt"))


def test_import_manifest_accepts_five_hundred_mib_boundary() -> None:
    boundary = 500 * 1024 * 1024
    assert ImportManifest.model_validate(manifest(byte_size=boundary)).byte_size == boundary

    with pytest.raises(ValidationError):
        ImportManifest.model_validate(manifest(byte_size=boundary + 1))


def test_import_batch_enforces_file_count_and_total_size() -> None:
    value = ImportBatchRequest.model_validate(
        {"collection_id": 1, "files": [manifest(), manifest(sha256="b" * 64, object_relpath=f"objects/{'b' * 64}")]}
    )
    assert len(value.files) == 2

    with pytest.raises(ValidationError):
        ImportBatchRequest.model_validate(
            {
                "collection_id": 1,
                "files": [
                    manifest(
                        sha256=f"{index:064x}",
                        object_relpath=f"objects/{index:064x}",
                    )
                    for index in range(51)
                ],
            }
        )
    with pytest.raises(ValidationError):
        ImportBatchRequest.model_validate(
            {
                "collection_id": 1,
                "files": [
                    manifest(byte_size=100 * 1024 * 1024),
                    manifest(
                        sha256="b" * 64,
                        object_relpath=f"objects/{'b' * 64}",
                        byte_size=100 * 1024 * 1024,
                    ),
                    manifest(
                        sha256="c" * 64,
                        object_relpath=f"objects/{'c' * 64}",
                        byte_size=100 * 1024 * 1024,
                    ),
                    manifest(
                        sha256="d" * 64,
                        object_relpath=f"objects/{'d' * 64}",
                        byte_size=100 * 1024 * 1024,
                    ),
                    manifest(
                        sha256="e" * 64,
                        object_relpath=f"objects/{'e' * 64}",
                        byte_size=100 * 1024 * 1024,
                    ),
                    manifest(
                        sha256="f" * 64,
                        object_relpath=f"objects/{'f' * 64}",
                        byte_size=1,
                    ),
                ],
            }
        )
