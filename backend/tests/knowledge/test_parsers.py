from __future__ import annotations

import asyncio
import zipfile
from pathlib import Path

import fitz
from openpyxl import Workbook
import pytest

from backend.knowledge.parsers import (
    KnowledgeParseError,
    ParserLimits,
    parse_document,
)
from backend.knowledge.import_service import DEFAULT_LIMITS, spawn_isolated_worker
from backend.knowledge.worker_protocol import (
    BlockEvent,
    DoneEvent,
    ProgressEvent,
    WorkerRequest,
    parse_worker_line,
)
from backend.tests.knowledge.fixtures.build_fixtures import (
    build_encrypted_pdf,
    build_supported_fixtures,
)


@pytest.fixture()
def fixtures(tmp_path: Path) -> Path:
    return build_supported_fixtures(tmp_path / "fixtures")


@pytest.mark.parametrize(
    ("name", "locator_type", "locator_start", "expected_text"),
    [
        ("lesson.pdf", "page", 1, "Newton second law"),
        ("lesson.docx", "paragraph", 1, "牛顿第二定律"),
        ("lesson.pptx", "slide", 1, "牛顿第二定律"),
        ("lesson.xlsx", "sheet_rows", 1, "概念"),
        ("lesson.csv", "sheet_rows", 1, "概念"),
        ("lesson.txt", "paragraph", 1, "牛顿第二定律"),
        ("lesson.md", "paragraph", 1, "牛顿第二定律"),
    ],
)
def test_supported_parser_preserves_text_and_locator(
    fixtures: Path,
    name: str,
    locator_type: str,
    locator_start: int,
    expected_text: str,
) -> None:
    result = parse_document(fixtures / name, ParserLimits())

    assert result.blocks
    assert any(expected_text in block.text for block in result.blocks)
    assert result.blocks[0].locator_type == locator_type
    assert result.blocks[0].locator_start == locator_start
    assert result.text_characters > 0


def test_markdown_preserves_heading_path(fixtures: Path) -> None:
    result = parse_document(fixtures / "lesson.md", ParserLimits())
    formula = next(block for block in result.blocks if "F = ma" in block.text)
    assert formula.heading_path == ("第一章", "公式")


@pytest.mark.parametrize(
    ("extension", "content"),
    [
        (".txt", "第一段\n\n第二段"),
        (".md", "# 标题\n\n教材内容"),
        (".csv", "知识点,说明\n一次函数,斜率"),
    ],
)
def test_large_text_formats_do_not_use_whole_file_read_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    extension: str,
    content: str,
) -> None:
    path = tmp_path / f"streaming{extension}"
    path.write_text(content, encoding="utf-8")

    def reject_whole_file_read(_path: Path) -> bytes:
        raise AssertionError("text parsers must not read the whole file into bytes")

    monkeypatch.setattr(Path, "read_bytes", reject_whole_file_read)

    result = parse_document(path, ParserLimits())

    assert result.blocks
    assert result.text_characters > 0


def test_blank_pdf_is_marked_for_ocr(tmp_path: Path) -> None:
    path = tmp_path / "blank.pdf"
    pdf = fitz.open()
    pdf.new_page()
    pdf.save(path)
    pdf.close()

    result = parse_document(path, ParserLimits())

    assert result.ocr_required is True
    assert result.page_count == 1


def test_pdf_parser_reports_page_progress_before_completion(tmp_path: Path) -> None:
    path = tmp_path / "progress.pdf"
    pdf = fitz.open()
    for index in range(3):
        page = pdf.new_page()
        page.insert_text((72, 72), f"Page {index + 1}")
    pdf.save(path)
    pdf.close()
    progress: list[tuple[int, int]] = []

    result = parse_document(
        path,
        ParserLimits(),
        progress_callback=lambda current, total: progress.append((current, total)),
    )

    assert result.page_count == 3
    assert progress == [(1, 3), (2, 3), (3, 3)]


def test_rejects_encrypted_pdf_and_fake_signature(tmp_path: Path) -> None:
    encrypted = build_encrypted_pdf(tmp_path / "encrypted.pdf")
    fake = tmp_path / "fake.pdf"
    fake.write_text("not pdf", encoding="utf-8")

    with pytest.raises(KnowledgeParseError) as encrypted_error:
        parse_document(encrypted, ParserLimits())
    assert encrypted_error.value.code == "KNOWLEDGE_DOCUMENT_ENCRYPTED"

    with pytest.raises(KnowledgeParseError) as fake_error:
        parse_document(fake, ParserLimits())
    assert fake_error.value.code == "KNOWLEDGE_FILE_SIGNATURE_MISMATCH"


def test_rejects_unsafe_zip_members_and_excessive_compression(tmp_path: Path) -> None:
    traversal = tmp_path / "traversal.docx"
    with zipfile.ZipFile(traversal, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("../escape.xml", "<escape/>")

    bomb = tmp_path / "bomb.docx"
    with zipfile.ZipFile(bomb, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", "A" * 100_000)

    with pytest.raises(KnowledgeParseError) as traversal_error:
        parse_document(traversal, ParserLimits())
    assert traversal_error.value.code == "KNOWLEDGE_ARCHIVE_UNSAFE"

    with pytest.raises(KnowledgeParseError) as bomb_error:
        parse_document(bomb, ParserLimits(max_compression_ratio=5))
    assert bomb_error.value.code == "KNOWLEDGE_ARCHIVE_UNSAFE"


def test_rejects_nul_text_csv_column_limit_and_sheet_limit(tmp_path: Path) -> None:
    nul_text = tmp_path / "nul.txt"
    nul_text.write_bytes(b"hello\0world")
    wide_csv = tmp_path / "wide.csv"
    wide_csv.write_text("a,b,c,d\n", encoding="utf-8")
    workbook_path = tmp_path / "many.xlsx"
    workbook = Workbook()
    workbook.create_sheet("Second")
    workbook.save(workbook_path)

    with pytest.raises(KnowledgeParseError) as nul_error:
        parse_document(nul_text, ParserLimits())
    assert nul_error.value.code == "KNOWLEDGE_PARSE_FAILED"

    with pytest.raises(KnowledgeParseError) as csv_error:
        parse_document(wide_csv, ParserLimits(max_csv_columns=3))
    assert csv_error.value.code == "KNOWLEDGE_PARSE_LIMIT_EXCEEDED"

    with pytest.raises(KnowledgeParseError) as sheet_error:
        parse_document(workbook_path, ParserLimits(max_sheets=1))
    assert sheet_error.value.code == "KNOWLEDGE_PARSE_LIMIT_EXCEEDED"


def test_rejects_xml_entities_before_office_library_parsing(tmp_path: Path) -> None:
    malicious = tmp_path / "entity.docx"
    with zipfile.ZipFile(malicious, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr(
            "word/document.xml",
            '<!DOCTYPE x [<!ENTITY secret SYSTEM "file:///secret">]><x>&secret;</x>',
        )

    with pytest.raises(KnowledgeParseError) as error:
        parse_document(malicious, ParserLimits())
    assert error.value.code == "KNOWLEDGE_ARCHIVE_UNSAFE"


def test_isolated_worker_parses_controlled_object_and_emits_jsonl(tmp_path: Path) -> None:
    async def exercise() -> None:
        digest = "a" * 64
        objects = tmp_path / "knowledge" / "objects"
        objects.mkdir(parents=True)
        (objects / digest).write_text("牛顿第二定律", encoding="utf-8")
        process = await spawn_isolated_worker(
            WorkerRequest(
                job_id=1,
                object_relpath=f"objects/{digest}",
                extension=".txt",
                limits=DEFAULT_LIMITS,
            ),
            object_root=objects,
        )
        assert process.stdout is not None
        events = []
        while line := await process.stdout.readline():
            events.append(parse_worker_line(line))
        assert await process.wait() == 0
        assert any(isinstance(event, BlockEvent) for event in events)
        assert isinstance(events[-1], DoneEvent)

    asyncio.run(exercise())


def test_isolated_pdf_worker_emits_page_progress_before_blocks(tmp_path: Path) -> None:
    async def exercise() -> None:
        digest = "b" * 64
        objects = tmp_path / "knowledge" / "objects"
        objects.mkdir(parents=True)
        pdf = fitz.open()
        for index in range(3):
            page = pdf.new_page()
            page.insert_text((72, 72), f"Page {index + 1}")
        pdf.save(objects / digest)
        pdf.close()
        process = await spawn_isolated_worker(
            WorkerRequest(
                job_id=1,
                object_relpath=f"objects/{digest}",
                extension=".pdf",
                limits=DEFAULT_LIMITS,
            ),
            object_root=objects,
        )
        assert process.stdout is not None
        events = []
        while line := await process.stdout.readline():
            events.append(parse_worker_line(line))
        assert await process.wait() == 0
        first_block = next(index for index, event in enumerate(events) if isinstance(event, BlockEvent))
        assert any(
            isinstance(event, ProgressEvent) and event.progress > 5
            for event in events[:first_block]
        )

    asyncio.run(exercise())
