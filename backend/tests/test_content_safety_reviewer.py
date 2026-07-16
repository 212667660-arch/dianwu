from types import SimpleNamespace

import pytest

from backend.errors import SafetyReviewUnavailableError
from backend.services.content_safety.models import (
    RiskCategory,
    RiskLevel,
    SafetyAction,
    SafetyStage,
)
from backend.services.content_safety.reviewer import (
    ReviewContext,
    SafetyReviewer,
    parse_reviewer_output,
)


ALLOW = """[协议 content-safety/v1]
stage: ARTIFACT
decision: ALLOW
risk_level: LOW
categories:
reason_codes: EDUCATIONAL_CONTEXT
[协议结束]"""

BLOCK = """[协议 content-safety/v1]
stage: ARTIFACT
decision: BLOCK
risk_level: HIGH
categories: CYBER_ABUSE|ILLEGAL_WRONGDOING
reason_codes: ACTIONABLE_MALWARE
[协议结束]"""


class FakeRouter:
    def __init__(self, candidates: tuple[str, ...], outputs: dict[str, object]) -> None:
        self.candidates = candidates
        self.outputs = outputs
        self.calls: list[dict[str, object]] = []

    def reviewer_candidate_ids(self, generation_profile_id=None):
        return self.candidates

    async def complete(self, selection, messages, temperature):
        profile_id = selection.preferred_profile_id
        self.calls.append({
            "profile_id": profile_id,
            "messages": messages,
            "temperature": temperature,
            "failover_enabled": selection.failover_enabled,
        })
        output = self.outputs[profile_id]
        if isinstance(output, BaseException):
            raise output
        return SimpleNamespace(text=output, profile_id=profile_id)


def context() -> ReviewContext:
    return ReviewContext(
        stage=SafetyStage.ARTIFACT,
        intent="生成防御性学习资料",
        subject_category="cs",
        artifact_type="course_explanation",
        audience="student",
    )


def test_parse_reviewer_output_accepts_only_controlled_protocol():
    metadata = parse_reviewer_output(BLOCK, reviewer_profile_id="reviewer")

    assert metadata.decision == SafetyAction.BLOCK
    assert metadata.risk_level == RiskLevel.HIGH
    assert metadata.categories == [
        RiskCategory.CYBER_ABUSE,
        RiskCategory.ILLEGAL_WRONGDOING,
    ]
    assert metadata.reviewer_profile_id == "reviewer"


@pytest.mark.parametrize(
    "invalid",
    [
        ALLOW + "\nfree explanation",
        ALLOW.replace("decision: ALLOW", "decision: MAYBE"),
        ALLOW.replace("stage: ARTIFACT", "stage: UNKNOWN"),
        ALLOW.replace("reason_codes: EDUCATIONAL_CONTEXT", "reason_codes: unsafe text"),
    ],
)
def test_parse_reviewer_output_rejects_free_text_and_invalid_enums(invalid):
    with pytest.raises(ValueError):
        parse_reviewer_output(invalid, reviewer_profile_id="reviewer")


@pytest.mark.asyncio
async def test_reviewer_prefers_enabled_non_generation_profile():
    router = FakeRouter(("backup", "primary"), {"backup": ALLOW, "primary": BLOCK})
    reviewer = SafetyReviewer(router=router)

    result = await reviewer.review(
        candidate="解释勒索软件的防御思路",
        generation_profile_id="primary",
        context=context(),
    )

    assert result.metadata.decision == SafetyAction.ALLOW
    assert result.metadata.reviewer_profile_id == "backup"
    assert [call["profile_id"] for call in router.calls] == ["backup"]


@pytest.mark.asyncio
async def test_reviewer_falls_back_to_same_profile_with_zero_temperature():
    router = FakeRouter(("primary",), {"primary": ALLOW})
    reviewer = SafetyReviewer(router=router)

    await reviewer.review(
        candidate="历史暴力教学",
        generation_profile_id="primary",
        context=context(),
    )

    assert router.calls[0]["temperature"] == 0.0
    assert router.calls[0]["failover_enabled"] is False


@pytest.mark.asyncio
async def test_candidate_content_is_untrusted_and_absent_from_system():
    marker = "UNTRUSTED-CANDIDATE"
    router = FakeRouter(("reviewer",), {"reviewer": ALLOW})

    await SafetyReviewer(router=router).review(candidate=marker, context=context())

    messages = router.calls[0]["messages"]
    system = "\n".join(item["content"] for item in messages if item["role"] == "system")
    user = "\n".join(item["content"] for item in messages if item["role"] == "user")
    assert marker not in system
    assert marker in user
    assert 'trust="untrusted"' in user


def test_reviewer_messages_fail_closed_instead_of_truncating_candidate_tail():
    from backend.services.content_safety.reviewer import build_reviewer_messages

    candidate = ("\\" * 70_000) + "DANGEROUS-TAIL"

    with pytest.raises(ValueError):
        build_reviewer_messages(candidate, context())


@pytest.mark.asyncio
async def test_oversized_reviewer_candidate_uses_stable_fail_closed_error():
    router = FakeRouter(("reviewer",), {"reviewer": ALLOW})

    with pytest.raises(SafetyReviewUnavailableError):
        await SafetyReviewer(router=router).review(
            candidate=("\\" * 70_000) + "DANGEROUS-TAIL",
            context=context(),
        )

    assert router.calls == []


@pytest.mark.asyncio
async def test_invalid_or_unavailable_reviewer_candidates_fail_closed():
    router = FakeRouter(
        ("backup", "primary"),
        {"backup": RuntimeError("offline"), "primary": "malformed"},
    )

    with pytest.raises(SafetyReviewUnavailableError):
        await SafetyReviewer(router=router).review(candidate="text", context=context())

    assert [call["profile_id"] for call in router.calls] == ["backup", "primary"]
