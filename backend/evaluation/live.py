from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path

from backend.config import get_settings
from backend.evaluation.history import record_report
from backend.evaluation.runner import (
    evaluate_profile_output,
    evaluate_resource_output,
    load_cases,
    save_report,
    summarize,
)
from backend.services.llm_service import ModelGateway
from backend.services.profile_agent import build_profile_messages
from backend.services.resource_agent import build_resource_messages

EVALUATION_PROFILE = """【协议:learner-profile/v1】
画像版本：1
年级：未明确
学科：未明确
当前水平：未明确
薄弱知识点：未明确
学习风格偏好：未明确
学习风格证据：评测输入未提供的信息保持未明确
认知层次：未明确
学习目标：未明确
推荐难度：基础
置信度：0.50
待确认问题：无
【协议结束】"""


async def run_live_evaluation(cases_path: str | Path, gateway: ModelGateway | None = None) -> tuple[dict[str, object], dict[str, str]]:
    settings = get_settings()
    if not settings.is_model_configured:
        raise RuntimeError("模型尚未配置，无法运行真实评测。请先配置 MODEL_PROVIDER、MODEL_API_KEY、MODEL_BASE_URL 和 MODEL_NAME。")
    cases = load_cases(cases_path)
    active_gateway = gateway or ModelGateway(settings)
    outputs: dict[str, str] = {}
    results = []
    execution: list[dict[str, object]] = []
    try:
        for case in cases:
            case_id = str(case["case_id"])
            started = time.perf_counter()
            try:
                if case["kind"] == "profile":
                    output = await active_gateway.complete(build_profile_messages([str(case["input"])], 1), temperature=0)
                    result = evaluate_profile_output(case, output)
                elif case["kind"] == "resource":
                    output = await active_gateway.complete(build_resource_messages(EVALUATION_PROFILE, str(case["input"])), temperature=0)
                    result = evaluate_resource_output(case, output)
                else:
                    raise ValueError(f"未知评测类型：{case['kind']}")
                outputs[case_id] = output
                results.append(result)
                execution.append({"case_id": case_id, "status": "completed", "elapsed_ms": round((time.perf_counter() - started) * 1000)})
            except Exception as exc:
                execution.append({"case_id": case_id, "status": "failed", "elapsed_ms": round((time.perf_counter() - started) * 1000), "error": getattr(exc, "code", type(exc).__name__)})
        report = summarize(results)
        report.update({
            "provider": settings.resolved_provider,
            "model_name": settings.resolved_model_name,
            "executions": execution,
            "completed_case_count": len(results),
            "failed_case_count": len(cases) - len(results),
        })
        return report, outputs
    finally:
        await active_gateway.aclose()


def main() -> int:
    parser = argparse.ArgumentParser(description="A3 当前模型真实评测")
    parser.add_argument("--cases", default=str(Path(__file__).with_name("cases.json")))
    parser.add_argument("--report", default="live-evaluation-report.json")
    parser.add_argument("--outputs", default="live-evaluation-outputs.json")
    parser.add_argument("--history-dir", default="live-evaluation-history", help="带时间戳的历史报告目录")
    parser.add_argument("--max-drop", type=float, default=3.0, help="相对上次评测允许的平均分下降上限")
    args = parser.parse_args()
    try:
        report, outputs = asyncio.run(run_live_evaluation(args.cases))
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    save_report(args.outputs, outputs)
    report, history_path = record_report(report, args.history_dir, max_drop=args.max_drop)
    save_report(args.report, report)
    print(json.dumps({**report, "history_report": str(history_path)}, ensure_ascii=False, indent=2))
    trend = report.get("trend_comparison")
    return 1 if report["failed_case_count"] or (trend and not trend["passed"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
