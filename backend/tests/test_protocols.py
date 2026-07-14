import pytest

from backend.errors import ProtocolValidationError
from backend.protocols import parse_diagnosis_decision, parse_profile, parse_resource, serialize_profile


PROFILE_TEXT = """【协议:learner-profile/v1】
画像版本：1
年级：初二
学科：数学
当前水平：基础
薄弱知识点：一次函数图像｜待定系数法
学习风格偏好：视觉型
学习风格证据：喜欢通过图像理解变化
认知层次：理解
学习目标：掌握一次函数基础题
推荐难度：基础｜提高
置信度：0.80
待确认问题：无
【协议结束】"""


RESOURCE_TEXT = """【协议:learning-resource/v1】
主题：一次函数
画像版本：1
资源类型：笔记｜练习
目标难度：基础｜提高
【学习笔记】
一次函数写作 y=kx+b。
【分层练习:基础】
题目1：求 y=2x+1 的截距。
答案1：1
解析1：令 x=0。
【协议结束】"""


DIAGNOSIS_TEXT = """【协议:diagnosis-decision/v1】
状态：CONTINUE
当前轮次：第 2 轮
已确认字段：学科｜学习目标
缺失字段：当前水平
置信度：80%
下一问题：你目前最容易在哪一步出错？
完成理由：还需确认当前水平。
【协议结束】"""


def test_profile_round_trip() -> None:
    profile = parse_profile(PROFILE_TEXT)
    canonical = serialize_profile(profile)
    assert parse_profile(canonical).subject == "数学"
    assert "薄弱知识点：一次函数图像｜待定系数法" in canonical


def test_profile_requires_protocol_header() -> None:
    with pytest.raises(ProtocolValidationError) as exc_info:
        parse_profile(PROFILE_TEXT.replace("【协议:learner-profile/v1】\n", "", 1))
    assert exc_info.value.code == "PROTOCOL_HEADER_MISSING"


def test_resource_requires_answer_and_explanation() -> None:
    broken = RESOURCE_TEXT.replace("解析1：令 x=0。\n", "")
    with pytest.raises(ProtocolValidationError) as exc_info:
        parse_resource(broken)
    assert exc_info.value.code == "QUESTION_TRIPLET_BROKEN"


def test_resource_parser_accepts_valid_sections() -> None:
    resource = parse_resource(RESOURCE_TEXT)
    assert resource.topic == "一次函数"
    assert "【学习笔记】" in resource.content
    assert resource.questions[0].prompt == "求 y=2x+1 的截距。"
    assert resource.questions[0].answer == "1"
    assert resource.questions[0].difficulty == "基础"


def test_resource_requires_nonempty_learning_note() -> None:
    broken = RESOURCE_TEXT.replace("一次函数写作 y=kx+b。\n", "")
    with pytest.raises(ProtocolValidationError) as exc_info:
        parse_resource(broken)
    assert exc_info.value.code == "NOTE_CONTENT_REQUIRED"


def test_resource_requires_at_least_one_question() -> None:
    broken = RESOURCE_TEXT.replace("题目1：求 y=2x+1 的截距。\n答案1：1\n解析1：令 x=0。\n", "")
    with pytest.raises(ProtocolValidationError) as exc_info:
        parse_resource(broken)
    assert exc_info.value.code == "QUESTION_REQUIRED"


def test_profile_prompt_preserves_explicit_level_instruction() -> None:
    from backend.services.profile_agent import build_profile_messages

    system_prompt = build_profile_messages(["我有编程基础"], 1)[0]["content"]
    assert "不能擅自升降级" in system_prompt


def test_diagnosis_parser_accepts_common_turn_and_percent_formats() -> None:
    decision = parse_diagnosis_decision(DIAGNOSIS_TEXT)
    assert decision.current_turn == 2
    assert decision.confidence == 0.8
