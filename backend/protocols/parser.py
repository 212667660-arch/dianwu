from __future__ import annotations

import re
from collections.abc import Callable

from pydantic import ValidationError

from backend.errors import ProtocolValidationError
from backend.protocols.models import DiagnosisDecision, LearnerProfile, LearningResource, PracticeQuestion

_END = "【协议结束】"
_TURN_VALUE = re.compile(r"第?\s*(\d+)\s*轮?")
_PERCENT_VALUE = re.compile(r"([0-9]+(?:\.\d+)?)\s*[%％]")


def _split_list(value: str) -> list[str]:
    if value in {"无", "未明确"}:
        return [value]
    return [item.strip() for item in value.split("｜") if item.strip()]


def _parse_turn(value: str) -> int:
    normalized = value.strip()
    match = _TURN_VALUE.fullmatch(normalized)
    if match is not None:
        return int(match.group(1))
    return int(normalized)


def _parse_confidence(value: str) -> float:
    normalized = value.strip()
    match = _PERCENT_VALUE.fullmatch(normalized)
    if match is not None:
        return float(match.group(1)) / 100
    return float(normalized)


def _unwrap(text: str, protocol: str) -> list[str]:
    lines = [line.rstrip() for line in text.strip().splitlines()]
    if not lines or lines[0] != f"【协议:{protocol}】":
        raise ProtocolValidationError("PROTOCOL_HEADER_MISSING", "模型返回的协议头无效。")
    if lines[-1] != _END:
        raise ProtocolValidationError("PROTOCOL_END_MISSING", "模型返回缺少协议结束标记。")
    return lines[1:-1]


def _fields(lines: list[str], allowed: dict[str, str]) -> tuple[dict[str, str], list[str]]:
    values: dict[str, str] = {}
    rest: list[str] = []
    for line in lines:
        if "：" not in line:
            rest.append(line)
            continue
        name, value = line.split("：", 1)
        if name not in allowed:
            rest.append(line)
            continue
        if name in values:
            raise ProtocolValidationError("FIELD_DUPLICATED", f"字段重复：{name}")
        values[name] = value.strip()
    for name in allowed:
        if not values.get(name):
            raise ProtocolValidationError("FIELD_REQUIRED", f"缺少字段：{name}")
    return values, rest


def _build(factory: Callable[..., object], data: dict[str, object]) -> object:
    try:
        return factory(**data)
    except ValidationError as exc:
        raise ProtocolValidationError("FIELD_INVALID", "模型返回字段不符合约束。") from exc


def parse_diagnosis_decision(text: str) -> DiagnosisDecision:
    fields, rest = _fields(_unwrap(text, "diagnosis-decision/v1"), {
        "状态": "status", "当前轮次": "current_turn", "已确认字段": "confirmed_fields",
        "缺失字段": "missing_fields", "置信度": "confidence", "下一问题": "next_question", "完成理由": "reason",
    })
    if rest:
        raise ProtocolValidationError("PROTOCOL_CONTENT_INVALID", "诊断协议包含未识别内容。")
    try:
        decision = _build(DiagnosisDecision, {
            "status": fields["状态"], "current_turn": _parse_turn(fields["当前轮次"]),
            "confirmed_fields": _split_list(fields["已确认字段"]),
            "missing_fields": _split_list(fields["缺失字段"]),
            "confidence": _parse_confidence(fields["置信度"]), "next_question": fields["下一问题"],
            "reason": fields["完成理由"],
        })
    except ValueError as exc:
        raise ProtocolValidationError("FIELD_INVALID_NUMBER", "诊断协议数字字段无效。") from exc
    if decision.status == "CONTINUE" and decision.next_question == "无":
        raise ProtocolValidationError("FIELD_REQUIRED", "继续诊断时必须给出下一问题。")
    return decision


def parse_profile(text: str) -> LearnerProfile:
    fields, rest = _fields(_unwrap(text, "learner-profile/v1"), {
        "画像版本": "profile_version", "年级": "grade", "学科": "subject", "当前水平": "current_level",
        "薄弱知识点": "weaknesses", "学习风格偏好": "learning_style", "学习风格证据": "style_evidence",
        "认知层次": "cognitive_level", "学习目标": "goal", "推荐难度": "recommended_difficulties",
        "置信度": "confidence", "待确认问题": "pending_question",
    })
    if rest:
        raise ProtocolValidationError("PROTOCOL_CONTENT_INVALID", "画像协议包含未识别内容。")
    try:
        return _build(LearnerProfile, {
            "profile_version": int(fields["画像版本"]), "grade": fields["年级"],
            "subject": fields["学科"], "current_level": fields["当前水平"],
            "weaknesses": _split_list(fields["薄弱知识点"]), "learning_style": fields["学习风格偏好"],
            "style_evidence": fields["学习风格证据"], "cognitive_level": fields["认知层次"],
            "goal": fields["学习目标"], "recommended_difficulties": _split_list(fields["推荐难度"]),
            "confidence": _parse_confidence(fields["置信度"]), "pending_question": fields["待确认问题"],
        })
    except ValueError as exc:
        raise ProtocolValidationError("FIELD_INVALID_NUMBER", "画像协议数字字段无效。") from exc


def parse_resource(text: str) -> LearningResource:
    fields, rest = _fields(_unwrap(text, "learning-resource/v1"), {
        "主题": "topic", "画像版本": "profile_version", "资源类型": "resource_types", "目标难度": "difficulties",
    })
    content = "\n".join(line for line in rest if line.strip()).strip()
    if "【学习笔记】" not in content:
        raise ProtocolValidationError("NOTE_SECTION_REQUIRED", "学习资源缺少学习笔记区块。")
    note_section = content.split("【学习笔记】", 1)[1].split("【分层练习:", 1)[0].strip()
    if not note_section:
        raise ProtocolValidationError("NOTE_CONTENT_REQUIRED", "学习笔记区块不能为空。")
    if "【分层练习:" not in content:
        raise ProtocolValidationError("PRACTICE_SECTION_REQUIRED", "学习资源缺少分层练习区块。")
    question_numbers = re.findall(r"题目(\d+)：", content)
    if not question_numbers:
        raise ProtocolValidationError("QUESTION_REQUIRED", "学习资源至少需要一道分层练习题。")
    if len(question_numbers) != len(set(question_numbers)):
        raise ProtocolValidationError("QUESTION_DUPLICATED", "练习题序号不能重复。")
    for number in question_numbers:
        if f"答案{number}：" not in content or f"解析{number}：" not in content:
            raise ProtocolValidationError("QUESTION_TRIPLET_BROKEN", "练习题必须包含题目、答案和解析。")
    questions = _parse_practice_questions(content, question_numbers)
    try:
        return _build(LearningResource, {
            "topic": fields["主题"], "profile_version": int(fields["画像版本"]),
            "resource_types": _split_list(fields["资源类型"]), "difficulties": _split_list(fields["目标难度"]),
            "content": content, "questions": questions,
        })
    except ValueError as exc:
        raise ProtocolValidationError("FIELD_INVALID_NUMBER", "资源协议画像版本无效。") from exc


def _parse_practice_questions(content: str, question_numbers: list[str]) -> list[PracticeQuestion]:
    sections = [(match.start(), match.group(1)) for match in re.finditer(r"【分层练习:(基础|提高|挑战)】", content)]
    questions: list[PracticeQuestion] = []
    for index, number in enumerate(question_numbers):
        question_marker = f"题目{number}："
        answer_marker = f"答案{number}："
        explanation_marker = f"解析{number}："
        question_start = content.find(question_marker)
        answer_start = content.find(answer_marker, question_start + len(question_marker))
        explanation_start = content.find(explanation_marker, answer_start + len(answer_marker))
        if not (question_start >= 0 and answer_start > question_start and explanation_start > answer_start):
            raise ProtocolValidationError("QUESTION_TRIPLET_BROKEN", "练习题字段顺序无效。")
        next_question_start = (
            content.find(f"题目{question_numbers[index + 1]}：", explanation_start + len(explanation_marker))
            if index + 1 < len(question_numbers)
            else -1
        )
        next_section_start = content.find("【分层练习:", explanation_start + len(explanation_marker))
        endings = [position for position in (next_question_start, next_section_start) if position >= 0]
        explanation_end = min(endings) if endings else len(content)
        difficulty = next((name for position, name in reversed(sections) if position < question_start), None)
        if difficulty is None:
            raise ProtocolValidationError("PRACTICE_SECTION_REQUIRED", "练习题必须位于难度区块中。")
        question = _build(PracticeQuestion, {
            "ordinal": int(number),
            "difficulty": difficulty,
            "prompt": content[question_start + len(question_marker):answer_start].strip(),
            "answer": content[answer_start + len(answer_marker):explanation_start].strip(),
            "explanation": content[explanation_start + len(explanation_marker):explanation_end].strip(),
        })
        questions.append(question)
    return questions


def serialize_profile(profile: LearnerProfile) -> str:
    return "\n".join([
        "【协议:learner-profile/v1】", f"画像版本：{profile.profile_version}", f"年级：{profile.grade}",
        f"学科：{profile.subject}", f"当前水平：{profile.current_level}", f"薄弱知识点：{'｜'.join(profile.weaknesses)}",
        f"学习风格偏好：{profile.learning_style}", f"学习风格证据：{profile.style_evidence}",
        f"认知层次：{profile.cognitive_level}", f"学习目标：{profile.goal}",
        f"推荐难度：{'｜'.join(profile.recommended_difficulties)}", f"置信度：{profile.confidence:.2f}",
        f"待确认问题：{profile.pending_question}", _END,
    ])


def serialize_resource(resource: LearningResource) -> str:
    return "\n".join([
        "【协议:learning-resource/v1】", f"主题：{resource.topic}", f"画像版本：{resource.profile_version}",
        f"资源类型：{'｜'.join(resource.resource_types)}", f"目标难度：{'｜'.join(resource.difficulties)}",
        resource.content, _END,
    ])
