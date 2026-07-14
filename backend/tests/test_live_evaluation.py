import asyncio
import json
from pathlib import Path

from backend.config import Settings
from backend.evaluation.live import run_live_evaluation
from backend.services.llm_service import ModelGateway

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
一次函数可写为 y=kx+b。
【分层练习:基础】
题目1：求截距。
答案1：1
解析1：令 x=0。
【分层练习:提高】
题目2：判断图像变化。
答案2：斜率为正时递增。
解析2：斜率决定图像方向。
【协议结束】"""


PROFILES = {
    "一次函数": PROFILE,
    "英语时态": """【协议:learner-profile/v1】
画像版本：1
年级：高中
学科：英语
当前水平：中等
薄弱知识点：时态
学习风格偏好：读写型
学习风格证据：偏好文字总结
认知层次：应用
学习目标：提高写作准确性
推荐难度：提高
置信度：0.80
待确认问题：无
【协议结束】""",
    "牛顿定律": """【协议:learner-profile/v1】
画像版本：1
年级：初中
学科：物理
当前水平：入门
薄弱知识点：牛顿定律
学习风格偏好：听觉型
学习风格证据：偏好讲解
认知层次：理解
学习目标：掌握概念
推荐难度：基础
置信度：0.80
待确认问题：无
【协议结束】""",
    "Python 异步编程": """【协议:learner-profile/v1】
画像版本：1
年级：大学
学科：编程
当前水平：熟练
薄弱知识点：Python 异步编程
学习风格偏好：动觉型
学习风格证据：偏好边做边学
认知层次：分析
学习目标：深入理解异步编程
推荐难度：挑战
置信度：0.80
待确认问题：无
【协议结束】""",
}

class FakeGateway(ModelGateway):
    def __init__(self) -> None:
        super().__init__(Settings(model_provider="openai", model_api_key="test-key", model_base_url="https://example.test", model_name="test-model"))
        self.calls = 0
        self.closed = False

    async def complete(self, messages, temperature=0.2):
        self.calls += 1
        if "learner-profile/v1" not in messages[0]["content"]:
            return RESOURCE
        prompt = messages[-1]["content"]
        return next(value for keyword, value in PROFILES.items() if keyword in prompt)

    async def aclose(self) -> None:
        self.closed = True


def test_live_evaluation_collects_outputs_and_timings(monkeypatch) -> None:
    import backend.evaluation.live as live

    monkeypatch.setattr(live, "get_settings", lambda: Settings(model_provider="openai", model_api_key="test-key", model_base_url="https://example.test", model_name="test-model"))
    gateway = FakeGateway()
    cases = Path(__file__).parents[1] / "evaluation" / "cases.json"
    report, outputs = asyncio.run(run_live_evaluation(cases, gateway))
    case_count = len(json.loads(cases.read_text(encoding="utf-8")))
    assert report["completed_case_count"] == case_count
    assert report["failed_case_count"] == 0
    assert report["average_score"] == 100
    assert len(outputs) == case_count
    assert all(item["elapsed_ms"] >= 0 for item in report["executions"])
    assert gateway.calls == case_count
    assert gateway.closed is True


def test_live_evaluation_requires_configured_model(monkeypatch) -> None:
    import backend.evaluation.live as live

    monkeypatch.setattr(live, "get_settings", lambda: Settings(model_provider="openai", model_api_key="", openai_api_key="", hy_api_key="", model_base_url="", openai_base_url="", hy_base_url="", model_name="", openai_model="", hy_model=""))
    cases = Path(__file__).parents[1] / "evaluation" / "cases.json"
    try:
        asyncio.run(run_live_evaluation(cases))
    except RuntimeError as exc:
        assert "模型尚未配置" in str(exc)
    else:
        raise AssertionError("未配置模型时必须拒绝运行真实评测")
