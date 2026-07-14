from pathlib import Path

from backend.evaluation.runner import compare_to_baseline, evaluate_profile_output, evaluate_resource_output, load_cases, summarize

PROFILE = """【协议:learner-profile/v1】
画像版本：1
年级：初二
学科：数学
当前水平：基础
薄弱知识点：一次函数图像
学习风格偏好：视觉型
学习风格证据：偏好图像
认知层次：理解
学习目标：掌握一次函数
推荐难度：基础｜提高
置信度：0.80
待确认问题：无
【协议结束】"""

RESOURCE = """【协议:learning-resource/v1】
主题：一次函数
画像版本：1
资源类型：笔记｜练习
目标难度：基础｜提高
【学习笔记】
一次函数。
【分层练习:基础】
题目1：求截距。
答案1：1
解析1：令 x=0。
【协议结束】"""


def test_evaluation_runner_produces_repeatable_summary() -> None:
    cases = load_cases(Path(__file__).parents[1] / "evaluation" / "cases.json")
    results = [evaluate_profile_output(cases[0], PROFILE), evaluate_resource_output(cases[1], RESOURCE)]
    report = summarize(results)
    assert report["protocol_pass_rate"] == 1
    assert report["average_score"] == 100


def test_evaluation_detects_quality_regression() -> None:
    comparison = compare_to_baseline(
        {"average_score": 75, "protocol_pass_rate": 0.9},
        {"average_score": 80, "protocol_pass_rate": 1.0},
    )
    assert comparison["passed"] is False
    assert "average_score_regression" in comparison["failures"]
