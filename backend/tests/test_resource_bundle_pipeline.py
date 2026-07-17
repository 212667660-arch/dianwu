from __future__ import annotations

import asyncio
import uuid

import pytest

from backend.protocols.v2.models import (
    ArtifactStatus, ArtifactType, BundleStatus, ResourceBrief, SubjectCategory,
)
from backend.services.resource_bundle.cancel import cancel_bundle, cleanup_cancellation
from backend.services.resource_bundle.pipeline import BundlePipeline
from backend.tests.fake_model_gateway import ScriptedGateway


BRIEF = ResourceBrief(
    topic="测试主题", learning_objectives=["目标1"], target_difficulty="基础",
    weak_knowledge_points=[], style_constraints="", source_allowlist=[],
    subject_category=SubjectCategory.MATH,
)

PLAN_OUT = """[协议 resource-plan/v2]
主题: 测试主题
学习目标: 目标1
目标难度: 基础
薄弱知识点:
风格约束:
来源白名单:
学科类别: math
[协议结束]"""

GROUNDED_PLAN_OUT = """[协议 resource-plan/v2]
主题: 一次函数
学习目标: 会代入求值
目标难度: 基础
薄弱知识点:
风格约束:
来源白名单: 资料1
学科类别: math
[协议结束]"""

COURSE_OUT = """## 学习目标
目标
## 核心概念与定义
概念
## 公式与适用条件
公式
## 知识依赖
依赖
## 逐步讲解
讲解
## 常见题型与易错点
误区
## 个性化建议
建议"""

COURSE_REVIEW_BAD = COURSE_OUT + """
## 教材内容
证据说明不完整。
## 模型补充知识
错误引用[资料1]。
## 例题复核
$y=2x+1
代入 x=2。
## 结果检查
待检查。"""

COURSE_REVIEW_REPAIRED = COURSE_OUT + """
## 教材内容
一次函数的定义与例题依据见[资料1]。
## 模型补充知识
图像直观属于模型补充说明。
## 例题复核
$y=2x+1$
代入 $x=2$ 得 $y=2\\times2+1=5$。
## 结果检查
代回原式成立。"""

MERMAID_OUT = """## Mermaid
flowchart TD
  A[测试] --> B[结果]
## 大纲
- 测试
  - 结果"""

QB_OUT = """## 基础
题目1：测试
答案1：答案
解析1：
- 已知条件与目标：条件与目标
- 所用知识点：知识点
- 分步推导：推导
- 最终答案：答案
- 结果检查：检查
## 提高
题目2：测试
答案2：答案
解析2：
- 已知条件与目标：条件与目标
- 所用知识点：知识点
- 分步推导：推导
- 最终答案：答案
- 结果检查：检查
## 挑战
题目3：测试
答案3：答案
解析3：
- 已知条件与目标：条件与目标
- 所用知识点：知识点
- 分步推导：推导
- 最终答案：答案
- 结果检查：检查"""

READING_OUT = """## 延伸阅读
无可引用外部来源。"""

PRACTICE_OUT = """## 目标
测试
## 已知条件与目标
给定条件并完成目标
## 所用知识点
一次函数定义
## 分步推导
1. 代入条件
## 最终答案
答案
## 结果检查
代回成立
## 验收标准
通过
## 参考方法
方法"""


class TestPipelineSingleMode:
    @pytest.mark.asyncio
    async def test_single_course_explanation(self):
        gateway = ScriptedGateway(completions=[PLAN_OUT, COURSE_OUT])
        pipeline = BundlePipeline(gateway=gateway)
        result = await pipeline.run(
            bundle_id="test-single", mode="single",
            single_type=ArtifactType.COURSE_EXPLANATION,
            profile_text="画像", learning_context="", knowledge_context="",
            user_request="生成", source_allowlist=[], subject_category_hint="math",
            profile_version=1, learning_state_version="v1",
        )
        assert result.bundle.status == BundleStatus.COMPLETED
        assert len(result.bundle.artifacts) == 1

    @pytest.mark.asyncio
    async def test_plan_failure(self):
        gateway = ScriptedGateway(completions=["invalid output"])
        pipeline = BundlePipeline(gateway=gateway)
        result = await pipeline.run(
            bundle_id="test-plan-fail", mode="single",
            single_type=ArtifactType.COURSE_EXPLANATION,
            profile_text="画像", learning_context="", knowledge_context="",
            user_request="生成", source_allowlist=[], subject_category_hint="math",
            profile_version=1, learning_state_version="v1",
        )
        assert result.bundle.status == BundleStatus.FAILED

    @pytest.mark.asyncio
    async def test_emits_plan_progress_artifact_and_bundle_events(self):
        gateway = ScriptedGateway(completions=[PLAN_OUT, COURSE_OUT])
        pipeline = BundlePipeline(gateway=gateway)
        events: list[dict[str, object]] = []

        async def on_event(event: dict[str, object]) -> None:
            events.append(event)

        result = await pipeline.run(
            bundle_id="test-events",
            mode="single",
            single_type=ArtifactType.COURSE_EXPLANATION,
            profile_text="画像",
            learning_context="",
            knowledge_context="",
            user_request="生成",
            source_allowlist=[],
            subject_category_hint="math",
            profile_version=1,
            learning_state_version="v1",
            on_event=on_event,
        )

        assert result.bundle.status == BundleStatus.COMPLETED
        assert [event["event"] for event in events] == [
            "resource_plan",
            "resource_progress",
            "answer_review",
            "answer_review",
            "resource_artifact",
            "resource_progress",
            "resource_bundle",
        ]
        assert events[0]["topic"] == "测试主题"
        assert events[-1]["status"] == "COMPLETED"

    @pytest.mark.asyncio
    async def test_answer_reviewer_repairs_once_and_records_agent_verdict(self):
        gateway = ScriptedGateway(completions=[
            GROUNDED_PLAN_OUT,
            COURSE_REVIEW_BAD,
            COURSE_REVIEW_REPAIRED,
        ])
        pipeline = BundlePipeline(gateway=gateway)
        events: list[dict[str, object]] = []

        result = await pipeline.run(
            bundle_id="test-answer-review",
            mode="single",
            single_type=ArtifactType.COURSE_EXPLANATION,
            profile_text="画像",
            learning_context="",
            knowledge_context="[资料1] 一次函数教材",
            user_request="生成例题",
            source_allowlist=["资料1"],
            knowledge_sources=[{"reference_id": "资料1"}],
            subject_category_hint="math",
            profile_version=1,
            learning_state_version="v1",
            knowledge_scope={"document_id": 1, "page_start": 1, "page_end": 5, "search_mode": "focused"},
            on_event=events.append,
        )

        reviewed = result.bundle.artifacts[0]
        assert reviewed.status == ArtifactStatus.SUCCEEDED
        assert reviewed.body == COURSE_REVIEW_REPAIRED
        assert reviewed.type_specific_data["answer_review"]["status"] == "REPAIRED"
        assert reviewed.type_specific_data["answer_review"]["repair_attempted"] is True
        assert [event["status"] for event in events if event["event"] == "answer_review"] == [
            "STARTED", "REPAIRED",
        ]

    @pytest.mark.asyncio
    async def test_failed_plan_event_keeps_trusted_source_snapshots(self):
        gateway = ScriptedGateway(completions=[])
        pipeline = BundlePipeline(gateway=gateway)
        events: list[dict[str, object]] = []

        result = await pipeline.run(
            bundle_id="test-plan-source-snapshots",
            mode="single",
            single_type=ArtifactType.COURSE_EXPLANATION,
            profile_text="画像",
            learning_context="",
            knowledge_context="",
            user_request="生成",
            source_allowlist=["资料1", "资料2"],
            subject_category_hint="math",
            profile_version=1,
            learning_state_version="v1",
            knowledge_sources=[{"reference_id": "资料1"}],
            public_sources=[{"reference_id": "资料2"}],
            on_event=events.append,
        )

        assert result.bundle.status == BundleStatus.FAILED
        assert result.bundle.knowledge_sources == [{"reference_id": "资料1"}]
        assert result.bundle.public_sources == [{"reference_id": "资料2"}]
        assert events[-1]["knowledge_sources"] == [{"reference_id": "资料1"}]
        assert events[-1]["public_sources"] == [{"reference_id": "资料2"}]


class TestPipelineBundleMode:
    @pytest.mark.asyncio
    async def test_all_five(self):
        gateway = ScriptedGateway(
            completions=[PLAN_OUT, COURSE_OUT, MERMAID_OUT, QB_OUT, READING_OUT, PRACTICE_OUT],
        )
        pipeline = BundlePipeline(gateway=gateway)
        result = await pipeline.run(
            bundle_id="test-all", mode="bundle", single_type=None,
            profile_text="画像", learning_context="", knowledge_context="",
            user_request="生成", source_allowlist=[], subject_category_hint="math",
            profile_version=1, learning_state_version="v1",
        )
        assert result.bundle.status == BundleStatus.COMPLETED
        assert len(result.bundle.artifacts) == 5

    @pytest.mark.asyncio
    async def test_partial_success(self):
        # mind_map (2nd specialist) gets the exception
        gateway = ScriptedGateway(
            completions=[PLAN_OUT, COURSE_OUT, Exception("MODEL_ERROR"), QB_OUT, READING_OUT, PRACTICE_OUT],
        )
        pipeline = BundlePipeline(gateway=gateway)
        result = await pipeline.run(
            bundle_id="test-partial", mode="bundle", single_type=None,
            profile_text="画像", learning_context="", knowledge_context="",
            user_request="生成", source_allowlist=[], subject_category_hint="math",
            profile_version=1, learning_state_version="v1",
        )
        assert result.bundle.status == BundleStatus.PARTIAL
        succeeded = [a for a in result.bundle.artifacts if a.status == ArtifactStatus.SUCCEEDED]
        failed = [a for a in result.bundle.artifacts if a.status == ArtifactStatus.FAILED]
        assert len(succeeded) >= 3
        assert len(failed) >= 1

    @pytest.mark.asyncio
    async def test_cancellation(self):
        gateway = ScriptedGateway(
            completions=[PLAN_OUT] + [COURSE_OUT] * 5,
        )
        pipeline = BundlePipeline(gateway=gateway)
        bundle_id = "test-cancel"

        async def _cancel():
            await asyncio.sleep(0.02)
            cancel_bundle(bundle_id)

        task = asyncio.create_task(pipeline.run(
            bundle_id=bundle_id, mode="bundle", single_type=None,
            profile_text="画像", learning_context="", knowledge_context="",
            user_request="生成", source_allowlist=[], subject_category_hint="math",
            profile_version=1, learning_state_version="v1",
        ))
        await asyncio.create_task(_cancel())
        result = await task
        cleanup_cancellation(bundle_id)
        assert result.bundle.status in (BundleStatus.CANCELLED, BundleStatus.PARTIAL)

    @pytest.mark.asyncio
    async def test_cancel_interrupts_running_specialist_completion(self):
        started = asyncio.Event()
        cancelled = asyncio.Event()

        class BlockingGateway:
            def __init__(self):
                self.calls = 0

            async def complete(self, messages, temperature=0.3):
                self.calls += 1
                if self.calls == 1:
                    return PLAN_OUT
                started.set()
                try:
                    await asyncio.Event().wait()
                except asyncio.CancelledError:
                    cancelled.set()
                    raise

        bundle_id = "test-running-cancel"
        pipeline = BundlePipeline(gateway=BlockingGateway())
        task = asyncio.create_task(pipeline.run(
            bundle_id=bundle_id,
            mode="bundle",
            single_type=None,
            profile_text="画像",
            learning_context="",
            knowledge_context="",
            user_request="生成",
            source_allowlist=[],
            subject_category_hint="math",
            profile_version=1,
            learning_state_version="v1",
        ))

        await asyncio.wait_for(started.wait(), timeout=1)
        cancel_bundle(bundle_id)
        result = await asyncio.wait_for(task, timeout=1)

        assert cancelled.is_set()
        assert result.bundle.status == BundleStatus.CANCELLED
        assert all(artifact.status == ArtifactStatus.CANCELLED for artifact in result.bundle.artifacts)
