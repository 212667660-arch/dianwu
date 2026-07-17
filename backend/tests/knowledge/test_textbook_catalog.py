from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.knowledge.schemas import TextbookCatalogItem
from backend.knowledge.textbook_catalog import list_textbooks


def item(**overrides) -> dict[str, object]:
    value: dict[str, object] = {
        "source_id": "pep-junior-math",
        "publisher": "人民教育出版社",
        "title": "人教版初中数学教材电子版目录",
        "stage": "初中",
        "grade": "七至九年级",
        "semester": "全册",
        "subject": "数学",
        "edition": "人教版",
        "official_url": "https://jc.pep.com.cn/?filed=初中&subject=数学",
        "access_mode": "OFFICIAL_READER",
        "license_note": "版权所有，仅打开出版社官方在线阅读页。",
        "verified_at": "2026-07-17",
        "download_url": None,
    }
    value.update(overrides)
    return value


def test_pep_catalog_entries_are_official_reader_only() -> None:
    junior = list_textbooks(stage="初中", subject="数学", publisher="人民教育出版社")
    high = list_textbooks(stage="高中", subject="数学", publisher="人民教育出版社")

    assert junior and high
    for entry in [*junior, *high]:
        assert entry.access_mode == "OFFICIAL_READER"
        assert entry.download_url is None
        assert entry.publisher == "人民教育出版社"
        assert entry.subject == "数学"


def test_catalog_item_rejects_unapproved_hosts_and_pep_downloads() -> None:
    with pytest.raises(ValidationError):
        TextbookCatalogItem.model_validate(item(official_url="https://attacker.example/book"))

    with pytest.raises(ValidationError):
        TextbookCatalogItem.model_validate(
            item(
                access_mode="LICENSED_DOWNLOAD",
                download_url="https://book.pep.com.cn/textbook.pdf",
            )
        )

