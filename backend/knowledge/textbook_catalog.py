from __future__ import annotations

from backend.knowledge.schemas import TextbookCatalogItem


_TEXTBOOKS = (
    TextbookCatalogItem(
        source_id="pep-junior-math",
        publisher="人民教育出版社",
        title="人教版初中数学教材电子版目录",
        stage="初中",
        grade="七至九年级",
        semester="全册",
        subject="数学",
        edition="人教版",
        official_url="https://jc.pep.com.cn/?filed=初中&subject=数学",
        access_mode="OFFICIAL_READER",
        license_note="版权所有，仅打开人民教育出版社官方在线阅读目录，不下载或镜像教材正文。",
        verified_at="2026-07-17",
        download_url=None,
    ),
    TextbookCatalogItem(
        source_id="pep-high-math",
        publisher="人民教育出版社",
        title="人教版高中数学教材电子版目录",
        stage="高中",
        grade="必修与选择性必修",
        semester="全册",
        subject="数学",
        edition="人教 A/B 版",
        official_url="https://jc.pep.com.cn/?filed=高中&subject=数学",
        access_mode="OFFICIAL_READER",
        license_note="版权所有，仅打开人民教育出版社官方在线阅读目录，不下载或镜像教材正文。",
        verified_at="2026-07-17",
        download_url=None,
    ),
)


def list_textbooks(
    stage: str | None = None,
    subject: str | None = None,
    publisher: str | None = None,
) -> list[TextbookCatalogItem]:
    return [
        item
        for item in _TEXTBOOKS
        if (stage is None or item.stage == stage)
        and (subject is None or item.subject == subject)
        and (publisher is None or item.publisher == publisher)
    ]
