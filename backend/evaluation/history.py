from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.evaluation.runner import compare_to_baseline, save_report


def timestamped_report_path(history_dir: str | Path, now: datetime | None = None) -> Path:
    instant = now or datetime.now(timezone.utc)
    return Path(history_dir) / f"live-{instant.strftime('%Y%m%dT%H%M%SZ')}.json"


def latest_report(history_dir: str | Path) -> Path | None:
    reports = sorted(Path(history_dir).glob("live-*.json"), reverse=True)
    return reports[0] if reports else None


def failure_summary(report: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for item in report.get("executions", []):
        if item.get("status") == "failed":
            lines.append(f"{item.get('case_id')}: 调用失败（{item.get('error', 'UNKNOWN')}）")
    for case_id, failures in dict(report.get("failures", {})).items():
        if failures:
            lines.append(f"{case_id}: 质量未达标（{', '.join(map(str, failures))}）")
    return lines


def record_report(report: dict[str, Any], history_dir: str | Path, max_drop: float = 3.0, now: datetime | None = None) -> tuple[dict[str, Any], Path]:
    directory = Path(history_dir)
    directory.mkdir(parents=True, exist_ok=True)
    previous_path = latest_report(directory)
    enriched = dict(report)
    enriched["recorded_at"] = (now or datetime.now(timezone.utc)).isoformat()
    enriched["failure_summary"] = failure_summary(enriched)
    if previous_path is not None:
        previous = json.loads(previous_path.read_text(encoding="utf-8"))
        enriched["trend_comparison"] = compare_to_baseline(enriched, previous, max_drop=max_drop)
        enriched["previous_report"] = previous_path.name
    else:
        enriched["trend_comparison"] = None
        enriched["previous_report"] = None
    destination = timestamped_report_path(directory, now)
    save_report(destination, enriched)
    return enriched, destination
