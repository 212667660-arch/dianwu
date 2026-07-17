from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from backend.database import SessionLocal, init_db
from backend.errors import ContentSafetyInputBlockedError
from backend.knowledge.context import KnowledgeContext
from backend.protocols.v2.models import ArtifactStatus, ArtifactType, BundleStatus
from backend.services import db as repo
from backend.services.content_safety.models import (
    RiskCategory,
    RiskLevel,
    SafetyAction,
    SafetyMetadata,
    SafetyStage,
)
from backend.services.content_safety.service import ContentSafetyService
from backend.services.resource_bundle.pipeline import BundlePipeline
from backend.services.resource_bundle.service import ResourceBundleService, ResourceSelection
from backend.services.resource_db import get_bundle_for_session
from backend.tests.fake_model_gateway import ScriptedGateway


PLAN_OUT = """[协议 resource-plan/v2]
主题: 测试主题
学习目标: 目标1
目标难度: 基础
薄弱知识点:
风格约束:
来源白名单:
学科类别: math
[协议结束]"""

UNSAFE_COURSE = """## 学习目标
目标
## 核心概念与定义
UNSAFE-ORIGINAL <script>alert(1)</script>
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

SAFE_COURSE = """## 学习目标
目标
## 核心概念与定义
安全概念
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

MERMAID_OUT = """## Mermaid
flowchart TD
  A[测试] --> B[结果]
## 大纲
- 测试
  - 结果"""

PII_MERMAID_OUT = """## Mermaid
flowchart TD
  A[联系 13800138000] --> B[学习]
## 大纲
- 联系 13800138000
  - 学习"""

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
无可引用外部来源，以下基于已有知识。"""

PRACTICE_OUT = """## 目标
测试
## 前置条件
无
## 步骤
1. 测试
## 验收标准
通过
## 参考方法
方法"""


def metadata(action: SafetyAction, reason_codes: list[str] | None = None) -> SafetyMetadata:
    return SafetyMetadata(
        stage=SafetyStage.ARTIFACT,
        decision=action,
        risk_level=RiskLevel.HIGH if action != SafetyAction.ALLOW else RiskLevel.LOW,
        categories=(
            [RiskCategory.ACTIVE_CONTENT_OR_UNSAFE_RENDERING]
            if action != SafetyAction.ALLOW
            else []
        ),
        reason_codes=reason_codes or [],
        reviewer_profile_id="reviewer",
        checked_at=datetime.now(timezone.utc).isoformat(),
    )


class AllowSafety:
    async def gate_request(self, text, **_kwargs):
        return SimpleNamespace(safe_text=text, metadata=metadata(SafetyAction.ALLOW))

    async def review_plan(self, _plan_text, **_kwargs):
        return metadata(SafetyAction.ALLOW)

    async def review_artifact(self, artifact, **_kwargs):
        safe = artifact.model_copy(update={"safety": metadata(SafetyAction.ALLOW)})
        return SimpleNamespace(
            action=SafetyAction.ALLOW,
            artifact=safe,
            metadata=safe.safety,
            reason_codes=[],
        )


class AuditCapturingSafety(AllowSafety):
    def __init__(self) -> None:
        self.plan_kwargs: list[dict[str, object]] = []
        self.artifact_kwargs: list[dict[str, object]] = []

    async def review_plan(self, _plan_text, **kwargs):
        self.plan_kwargs.append(kwargs)
        return await super().review_plan(_plan_text, **kwargs)

    async def review_artifact(self, artifact, **kwargs):
        self.artifact_kwargs.append(kwargs)
        return await super().review_artifact(artifact, **kwargs)


class AllowReviewer:
    async def review(self, *, candidate, generation_profile_id=None, context):
        return SimpleNamespace(
            metadata=SafetyMetadata(
                stage=context.stage,
                decision=SafetyAction.ALLOW,
                risk_level=RiskLevel.LOW,
                reviewer_profile_id="reviewer",
                checked_at=datetime.now(timezone.utc).isoformat(),
            )
        )


class DenyRequestSafety(AllowSafety):
    async def gate_request(self, text, **_kwargs):
        raise ContentSafetyInputBlockedError()


class RegenerateThenAllowSafety(AllowSafety):
    def __init__(self) -> None:
        self.artifact_bodies: list[str] = []

    async def review_artifact(self, artifact, **_kwargs):
        self.artifact_bodies.append(artifact.body)
        if len(self.artifact_bodies) == 1:
            blocked = metadata(SafetyAction.REGENERATE, ["ACTIVE_CONTENT_REGENERATE"])
            return SimpleNamespace(
                action=SafetyAction.REGENERATE,
                artifact=None,
                metadata=blocked,
                reason_codes=blocked.reason_codes,
            )
        return await super().review_artifact(artifact, **_kwargs)


class BlockCourseSafety(AllowSafety):
    async def review_artifact(self, artifact, **_kwargs):
        if artifact.type == ArtifactType.COURSE_EXPLANATION:
            blocked = metadata(SafetyAction.BLOCK, ["ACTIVE_CONTENT_BLOCKED"])
            return SimpleNamespace(
                action=SafetyAction.BLOCK,
                artifact=None,
                metadata=blocked,
                reason_codes=blocked.reason_codes,
            )
        return await super().review_artifact(artifact, **_kwargs)


def seed_profiled_session(session_id: str) -> None:
    init_db()
    with SessionLocal() as db:
        session = repo.get_or_create_session(db, session_id)
        session.state = repo.SessionState.PROFILED.value
        session.last_stable_state = repo.SessionState.PROFILED.value
        session.profile_text = "[协议:learner-profile/v1]\n画像版本：1\n年级：初二\n学科：数学\n当前水平：基础\n薄弱知识点：函数\n学习风格偏好：视觉型\n学习风格证据：自述\n认知层次：理解\n学习目标：掌握函数\n推荐难度：基础\n置信度：0.9\n待确认问题：\n[协议结束]"
        session.profile_version = 1
        repo.commit(db)


@pytest.mark.asyncio
async def test_blocked_request_never_calls_pipeline_or_persists_bundle():
    session_id = f"safety-block-{uuid.uuid4().hex[:8]}"
    seed_profiled_session(session_id)

    class CapturingPipeline:
        calls: list[dict[str, object]] = []

        async def run(self, **kwargs):
            self.calls.append(kwargs)
            raise AssertionError("pipeline must not run")

    pipeline = CapturingPipeline()
    service = ResourceBundleService(
        pipeline=pipeline,
        safety_service=DenyRequestSafety(),
        learning_context_provider=lambda _db, _sid: "",
        knowledge_retriever=lambda _db, _sid, _query: KnowledgeContext.empty(),
        web_search=lambda _message: async_value([]),
    )

    with SessionLocal() as db:
        with pytest.raises(ContentSafetyInputBlockedError):
            await service.generate(
                db,
                session_id,
                "危险请求",
                ResourceSelection.bundle(),
                generation_id="blocked-generation",
            )
        assert get_bundle_for_session(db, session_id, "bundle-blocked-generation") is None
    assert pipeline.calls == []


@pytest.mark.asyncio
async def test_regenerate_happens_once_without_reinjecting_rejected_output():
    safety = RegenerateThenAllowSafety()
    gateway = ScriptedGateway(completions=[PLAN_OUT, UNSAFE_COURSE, SAFE_COURSE])
    pipeline = BundlePipeline(gateway=gateway, safety_service=safety)

    result = await pipeline.run(
        bundle_id="bundle-regenerate",
        mode="single",
        single_type=ArtifactType.COURSE_EXPLANATION,
        profile_text="画像",
        learning_context="",
        knowledge_context="",
        user_request="生成防御性资料",
        source_allowlist=[],
        subject_category_hint="math",
        profile_version=1,
        learning_state_version="1",
    )

    assert result.bundle.status == BundleStatus.COMPLETED
    assert result.bundle.artifacts[0].body == SAFE_COURSE
    assert safety.artifact_bodies == [UNSAFE_COURSE, SAFE_COURSE]
    assert len(gateway.calls) == 3
    regeneration_messages = json.dumps(gateway.calls[2]["messages"], ensure_ascii=False)
    assert "UNSAFE-ORIGINAL" not in regeneration_messages
    assert "ACTIVE_CONTENT_REGENERATE" in regeneration_messages


@pytest.mark.asyncio
async def test_bundle_reviews_use_bundle_and_session_audit_identifiers():
    session_id = f"safety-audit-{uuid.uuid4().hex[:8]}"
    seed_profiled_session(session_id)
    safety = AuditCapturingSafety()
    service = ResourceBundleService(
        pipeline=BundlePipeline(
            gateway=ScriptedGateway(completions=[PLAN_OUT, SAFE_COURSE]),
            safety_service=safety,
        ),
        safety_service=safety,
        learning_context_provider=lambda _db, _sid: "",
        knowledge_retriever=lambda _db, _sid, _query: KnowledgeContext.empty(),
        web_search=lambda _message: async_value([]),
    )

    with SessionLocal() as db:
        bundle = await service.generate(
            db,
            session_id,
            "生成课程讲解",
            ResourceSelection.single(ArtifactType.COURSE_EXPLANATION),
            generation_id="audit-generation",
        )

    assert safety.plan_kwargs[0]["request_id"] == bundle.bundle_id
    assert safety.plan_kwargs[0]["session_tag"] == session_id
    assert safety.artifact_kwargs[0]["request_id"] == bundle.bundle_id
    assert safety.artifact_kwargs[0]["session_tag"] == session_id


@pytest.mark.asyncio
async def test_blocked_artifact_is_not_emitted_and_safe_siblings_form_partial_bundle():
    gateway = ScriptedGateway(completions=[
        PLAN_OUT,
        UNSAFE_COURSE,
        MERMAID_OUT,
        QB_OUT,
        READING_OUT,
        PRACTICE_OUT,
    ])
    events: list[dict[str, object]] = []
    pipeline = BundlePipeline(gateway=gateway, safety_service=BlockCourseSafety())

    result = await pipeline.run(
        bundle_id="bundle-partial-safety",
        mode="bundle",
        single_type=None,
        profile_text="画像",
        learning_context="",
        knowledge_context="",
        user_request="生成资源",
        source_allowlist=[],
        subject_category_hint="math",
        profile_version=1,
        learning_state_version="1",
        on_event=events.append,
    )

    blocked = next(
        artifact for artifact in result.bundle.artifacts
        if artifact.type == ArtifactType.COURSE_EXPLANATION
    )
    assert result.bundle.status == BundleStatus.PARTIAL
    assert blocked.status == ArtifactStatus.FAILED
    assert blocked.body == ""
    assert blocked.error_code == "CONTENT_ARTIFACT_BLOCKED"
    assert blocked.retryable is True
    assert any(artifact.status == ArtifactStatus.SUCCEEDED for artifact in result.bundle.artifacts)
    assert all("UNSAFE-ORIGINAL" not in json.dumps(event, ensure_ascii=False) for event in events)


@pytest.mark.asyncio
async def test_mind_map_type_data_is_redacted_before_sse_and_persistence():
    session_id = f"safety-mind-map-{uuid.uuid4().hex[:8]}"
    seed_profiled_session(session_id)
    safety = ContentSafetyService(reviewer=AllowReviewer())
    pipeline = BundlePipeline(
        gateway=ScriptedGateway(completions=[PLAN_OUT, PII_MERMAID_OUT]),
        safety_service=safety,
    )
    events: list[dict[str, object]] = []
    service = ResourceBundleService(
        pipeline=pipeline,
        safety_service=safety,
        learning_context_provider=lambda _db, _sid: "",
        knowledge_retriever=lambda _db, _sid, _query: KnowledgeContext.empty(),
        web_search=lambda _message: async_value([]),
    )

    with SessionLocal() as db:
        bundle = await service.generate(
            db,
            session_id,
            "生成思维导图",
            ResourceSelection.single(ArtifactType.MIND_MAP),
            generation_id="mind-map-redaction",
            on_event=events.append,
        )
        stored = get_bundle_for_session(db, session_id, bundle.bundle_id)

    artifact = bundle.artifacts[0]
    assert "13800138000" not in artifact.body
    assert "13800138000" not in str(artifact.type_specific_data)
    assert "13800138000" not in json.dumps(events, ensure_ascii=False)
    assert stored is not None
    assert "13800138000" not in json.dumps(stored, ensure_ascii=False)
    assert "[手机号已隐藏]" in artifact.type_specific_data["outline"]


async def async_value(value):
    return value
