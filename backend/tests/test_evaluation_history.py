import json
from datetime import datetime, timezone

from backend.evaluation.history import failure_summary, record_report


def _report(score: float, protocol: float = 1.0, failures=None, executions=None):
    return {
        "average_score": score,
        "protocol_pass_rate": protocol,
        "failures": failures or {},
        "executions": executions or [],
    }


def test_record_report_compares_to_previous_and_saves_timestamped_history(tmp_path) -> None:
    first, first_path = record_report(_report(100), tmp_path, now=datetime(2026, 7, 10, 1, 2, 3, tzinfo=timezone.utc))
    assert first["trend_comparison"] is None
    assert first_path.name == "live-20260710T010203Z.json"

    second, second_path = record_report(_report(94), tmp_path, max_drop=3, now=datetime(2026, 7, 10, 1, 2, 4, tzinfo=timezone.utc))
    assert second_path.name == "live-20260710T010204Z.json"
    assert second["previous_report"] == first_path.name
    assert second["trend_comparison"]["passed"] is False
    assert "average_score_regression" in second["trend_comparison"]["failures"]
    assert json.loads(second_path.read_text(encoding="utf-8"))["average_score"] == 94


def test_failure_summary_reports_transport_and_quality_failures() -> None:
    summary = failure_summary(_report(80, failures={"case-a": ["missing:subject"]}, executions=[{"case_id": "case-b", "status": "failed", "error": "MODEL_TIMEOUT"}]))
    assert "case-b: 调用失败（MODEL_TIMEOUT）" in summary
    assert "case-a: 质量未达标（missing:subject）" in summary
