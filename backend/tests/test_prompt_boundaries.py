from backend.protocols.v2.models import ArtifactType, ResourceBrief, SubjectCategory
from backend.services.profile_agent import build_diagnosis_messages, build_profile_messages
from backend.services.resource_agent import build_resource_messages
from backend.services.resource_bundle.planner import build_planner_messages
from backend.services.resource_bundle.specialists.base import (
    build_specialist_messages,
    specialist_for_type,
)


MARKER = "DYN-UNTRUSTED"


def _system_text(messages: list[dict[str, str]]) -> str:
    return "\n".join(message["content"] for message in messages if message["role"] == "system")


def _user_text(messages: list[dict[str, str]]) -> str:
    return "\n".join(message["content"] for message in messages if message["role"] == "user")


def _assert_boundary(messages: list[dict[str, str]]) -> None:
    assert MARKER not in _system_text(messages)
    assert MARKER in _user_text(messages)
    assert 'trust="untrusted"' in _user_text(messages)


def test_diagnosis_history_is_untrusted_user_data():
    _assert_boundary(build_diagnosis_messages([MARKER], 1))


def test_profile_history_is_untrusted_user_data():
    _assert_boundary(build_profile_messages([MARKER], 1))


def test_legacy_resource_dynamic_fields_are_untrusted_user_data():
    messages = build_resource_messages(
        MARKER,
        MARKER,
        [{"title": MARKER, "url": "https://example.test", "snippet": MARKER}],
        MARKER,
        MARKER,
    )

    _assert_boundary(messages)


def test_planner_dynamic_fields_are_untrusted_user_data():
    messages = build_planner_messages(
        MARKER,
        MARKER,
        MARKER,
        MARKER,
        [MARKER],
        MARKER,
    )

    _assert_boundary(messages)


def test_specialist_brief_and_context_are_untrusted_user_data():
    brief = ResourceBrief(
        topic=MARKER,
        learning_objectives=[MARKER],
        target_difficulty=MARKER,
        weak_knowledge_points=[MARKER],
        style_constraints=MARKER,
        source_allowlist=["资料1"],
        subject_category=SubjectCategory.OTHER,
    )
    messages = build_specialist_messages(
        ArtifactType.COURSE_EXPLANATION,
        brief,
        MARKER,
        MARKER,
        MARKER,
    )

    _assert_boundary(messages)


def test_every_concrete_specialist_keeps_brief_out_of_system_messages():
    brief = ResourceBrief(
        topic=MARKER,
        learning_objectives=[MARKER],
        target_difficulty=MARKER,
        weak_knowledge_points=[MARKER],
        style_constraints=MARKER,
        source_allowlist=["资料1"],
        subject_category=SubjectCategory.OTHER,
    )

    for artifact_type in ArtifactType:
        messages = specialist_for_type(artifact_type).build_prompt(
            brief,
            MARKER,
            MARKER,
            MARKER,
        )
        _assert_boundary(messages)


def test_planner_user_payload_has_a_bounded_total_size():
    messages = build_planner_messages(
        "p" * 20000,
        "l" * 20000,
        "k" * 20000,
        "r" * 8000,
        [f"资料{index}" for index in range(1, 51)],
        "other",
    )

    assert len(_user_text(messages)) <= 31000
