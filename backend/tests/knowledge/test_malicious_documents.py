from __future__ import annotations

import asyncio
from hashlib import sha256
from pathlib import Path
import shutil
import zipfile

from fastapi.testclient import TestClient
from openpyxl import Workbook
import pytest

from backend.knowledge.import_service import spawn_isolated_worker
from backend.knowledge.worker_protocol import FailureEvent, WorkerRequest, parse_worker_line
from backend.tests.knowledge.fixtures.build_fixtures import build_encrypted_pdf


def _build_fixture(root: Path, fixture_name: str) -> tuple[Path, str, dict[str, int | float]]:
    marker = "TOP_SECRET_BODY"
    if fixture_name == "zip_traversal":
        path = root / "traversal.docx"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("[Content_Types].xml", "<Types/>")
            archive.writestr("../escape.xml", marker)
        return path, ".docx", {}
    if fixture_name == "xml_entity":
        path = root / "entity.docx"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("[Content_Types].xml", "<Types/>")
            archive.writestr(
                "word/document.xml",
                f'<!DOCTYPE x [<!ENTITY secret SYSTEM "file:///secret">]><x>{marker}&secret;</x>',
            )
        return path, ".docx", {}
    if fixture_name == "fake_pdf":
        path = root / "fake.pdf"
        path.write_text(marker, encoding="utf-8")
        return path, ".pdf", {}
    if fixture_name == "encrypted_pdf":
        return build_encrypted_pdf(root / "encrypted.pdf"), ".pdf", {}
    if fixture_name == "nul_text":
        path = root / "nul.txt"
        path.write_bytes(marker.encode("utf-8") + b"\0hidden")
        return path, ".txt", {}
    if fixture_name in {"sheet_limit", "cell_limit"}:
        path = root / f"{fixture_name}.xlsx"
        workbook = Workbook()
        workbook.active.append([marker, "second"])
        if fixture_name == "sheet_limit":
            workbook.create_sheet("Second")
            limits = {"max_sheets": 1}
        else:
            limits = {"max_cells": 1}
        workbook.save(path)
        return path, ".xlsx", limits
    if fixture_name in {"row_limit", "column_limit"}:
        path = root / f"{fixture_name}.csv"
        path.write_text(f"{marker},a,b\nsecond,c,d\n", encoding="utf-8")
        limits = {"max_csv_rows": 1} if fixture_name == "row_limit" else {"max_csv_columns": 2}
        return path, ".csv", limits
    raise AssertionError(f"unknown fixture: {fixture_name}")


def _run_worker(source: Path, extension: str, limits: dict[str, int | float]) -> tuple[int, str]:
    async def exercise() -> tuple[int, str]:
        digest = sha256(source.read_bytes()).hexdigest()
        objects_root = source.parent / "knowledge" / "objects"
        objects_root.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, objects_root / digest)
        process = await spawn_isolated_worker(
            WorkerRequest(
                job_id=1,
                object_relpath=f"objects/{digest}",
                extension=extension,
                limits=limits,
            ),
            object_root=objects_root,
        )
        assert process.stdout is not None
        raw_lines = []
        while line := await process.stdout.readline():
            raw_lines.append(line)
        return await process.wait(), b"".join(raw_lines).decode("utf-8", errors="strict")

    return asyncio.run(exercise())


@pytest.mark.parametrize(
    ("fixture_name", "expected_code"),
    [
        ("zip_traversal", "KNOWLEDGE_ARCHIVE_UNSAFE"),
        ("xml_entity", "KNOWLEDGE_ARCHIVE_UNSAFE"),
        ("fake_pdf", "KNOWLEDGE_FILE_SIGNATURE_MISMATCH"),
        ("encrypted_pdf", "KNOWLEDGE_DOCUMENT_ENCRYPTED"),
        ("nul_text", "KNOWLEDGE_PARSE_FAILED"),
        ("sheet_limit", "KNOWLEDGE_PARSE_LIMIT_EXCEEDED"),
        ("cell_limit", "KNOWLEDGE_PARSE_LIMIT_EXCEEDED"),
        ("row_limit", "KNOWLEDGE_PARSE_LIMIT_EXCEEDED"),
        ("column_limit", "KNOWLEDGE_PARSE_LIMIT_EXCEEDED"),
    ],
)
def test_malicious_fixture_is_contained(
    tmp_path: Path,
    fixture_name: str,
    expected_code: str,
) -> None:
    source, extension, limits = _build_fixture(tmp_path, fixture_name)

    returncode, output = _run_worker(source, extension, limits)
    events = [parse_worker_line(line) for line in output.splitlines()]

    assert returncode == 2
    assert isinstance(events[-1], FailureEvent)
    assert events[-1].code == expected_code
    assert str(source) not in output
    assert "TOP_SECRET_BODY" not in output


def test_malicious_worker_failures_do_not_break_backend_liveness() -> None:
    from backend.main import app

    with TestClient(app) as client:
        response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "live"}
