from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from backend.errors import ProtocolValidationError
from backend.protocols import parse_profile, parse_resource


@dataclass
class EvaluationResult:
    case_id: str
    protocol_valid: bool
    score: int
    failures: list[str]


def load_cases(path: str | Path) -> list[dict[str, object]]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def evaluate_profile_output(case: dict[str, object], output: str) -> EvaluationResult:
    failures: list[str] = []
    try:
        profile = parse_profile(output)
    except ProtocolValidationError as exc:
        return EvaluationResult(str(case["case_id"]), False, 0, [exc.code])
    for field, expected in dict(case.get("expected", {})).items():
        if not hasattr(profile, field):
            failures.append(f"unknown:{field}")
            continue
        value = getattr(profile, field)
        if isinstance(value, list):
            if str(expected) not in value:
                failures.append(f"missing:{field}")
        elif str(expected) not in str(value):
            failures.append(f"mismatch:{field}")
    score = max(0, 100 - len(failures) * 20)
    return EvaluationResult(str(case["case_id"]), True, score, failures)


def evaluate_resource_output(case: dict[str, object], output: str) -> EvaluationResult:
    failures: list[str] = []
    try:
        resource = parse_resource(output)
    except ProtocolValidationError as exc:
        return EvaluationResult(str(case["case_id"]), False, 0, [exc.code])
    for required in case.get("required_sections", []):
        if str(required) not in resource.content:
            failures.append(f"missing:{required}")
    score = max(0, 100 - len(failures) * 25)
    return EvaluationResult(str(case["case_id"]), True, score, failures)


def summarize(results: list[EvaluationResult]) -> dict[str, object]:
    return {
        "case_count": len(results),
        "protocol_pass_rate": sum(item.protocol_valid for item in results) / len(results) if results else 0,
        "average_score": sum(item.score for item in results) / len(results) if results else 0,
        "failures": {item.case_id: item.failures for item in results if item.failures},
    }


def compare_to_baseline(report: dict[str, object], baseline: dict[str, object], max_drop: float = 3.0) -> dict[str, object]:
    current_score = float(report.get("average_score", 0))
    baseline_score = float(baseline.get("average_score", 0))
    current_protocol = float(report.get("protocol_pass_rate", 0))
    baseline_protocol = float(baseline.get("protocol_pass_rate", 0))
    failures: list[str] = []
    if current_score < baseline_score - max_drop:
        failures.append("average_score_regression")
    if current_protocol < baseline_protocol:
        failures.append("protocol_pass_rate_regression")
    return {"passed": not failures, "failures": failures, "score_delta": current_score - baseline_score}


def save_report(path: str | Path, report: dict[str, object]) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
