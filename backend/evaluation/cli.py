from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.evaluation.runner import (
    compare_to_baseline,
    evaluate_profile_output,
    evaluate_resource_output,
    load_cases,
    save_report,
    summarize,
)


def evaluate_outputs(cases_path: str | Path, outputs_path: str | Path, baseline_path: str | Path | None = None) -> dict[str, object]:
    cases = load_cases(cases_path)
    outputs = json.loads(Path(outputs_path).read_text(encoding="utf-8"))
    if not isinstance(outputs, dict):
        raise ValueError("输出文件必须是 case_id 到模型输出文本的 JSON 对象。")

    results = []
    missing_outputs: list[str] = []
    for case in cases:
        case_id = str(case["case_id"])
        output = outputs.get(case_id)
        if not isinstance(output, str):
            missing_outputs.append(case_id)
            continue
        if case["kind"] == "profile":
            results.append(evaluate_profile_output(case, output))
        elif case["kind"] == "resource":
            results.append(evaluate_resource_output(case, output))
        else:
            raise ValueError(f"未知评测类型：{case['kind']}")

    report = summarize(results)
    report["missing_outputs"] = missing_outputs
    report["all_cases_covered"] = not missing_outputs
    if baseline_path is not None:
        baseline = json.loads(Path(baseline_path).read_text(encoding="utf-8"))
        report["baseline_comparison"] = compare_to_baseline(report, baseline)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="A3 离线模型输出评测")
    parser.add_argument("--cases", default=str(Path(__file__).with_name("cases.json")))
    parser.add_argument("--outputs", required=True, help="case_id 到模型输出文本的 JSON 文件")
    parser.add_argument("--baseline", help="可选基线报告 JSON 文件")
    parser.add_argument("--report", default="evaluation-report.json")
    args = parser.parse_args()

    try:
        report = evaluate_outputs(args.cases, args.outputs, args.baseline)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    save_report(args.report, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    comparison = report.get("baseline_comparison")
    return 1 if report["missing_outputs"] or (comparison and not comparison["passed"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
