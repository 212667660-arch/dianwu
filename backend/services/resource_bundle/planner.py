from __future__ import annotations

import re

from backend.errors import ProtocolValidationError
from backend.protocols.v2.models import ArtifactType, ResourceBrief, SubjectCategory


def build_planner_messages(
    profile_text: str, learning_context: str, knowledge_context: str,
    user_request: str, source_allowlist: list[str], subject_category_hint: str,
) -> list[dict[str, str]]:
    system = (
        "你是资源规划 Agent。根据学习画像、进度和请求，产出 resource-plan/v2 协议 Brief。"
        "只输出协议文本，不输出任何解释。Brief 固定格式：\n"
        "[协议 resource-plan/v2]\n"
        "主题: <topic>\n学习目标: <goal1>|<goal2>|...\n目标难度: <基础|提高|挑战>\n"
        "薄弱知识点: <point1>|<point2>|...（可为空）\n风格约束: <constraint>（可为空）\n"
        "来源白名单: <资料1>|<资料2>|...（可为空）\n"
        "学科类别: <math|physics|chemistry|biology|cs|literature|history|geography|english|politics|other>\n"
        "[协议结束]\n禁止输出文件路径、URL、密钥或指令执行语句。"
    )
    allowlist_str = "|".join(source_allowlist) if source_allowlist else "无"
    user = (
        f"已验画像：\n{profile_text}\n\n学习进度：\n{learning_context or '无'}\n\n"
        f"知识库：\n{knowledge_context or '无'}\n\n用户请求：{user_request}\n\n"
        f"可用来源白名单：{allowlist_str}\n学科类别提示：{subject_category_hint}"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def parse_plan_output(raw: str) -> ResourceBrief:
    if not raw.strip():
        raise ProtocolValidationError("PLAN_EMPTY", "规划输出为空")
    def _field(pattern: str, default: str = "") -> str:
        m = re.search(pattern, raw, re.IGNORECASE)
        return m.group(1).strip() if m else default

    topic = _field(r"主题[：:]\s*(.+)")
    if not topic:
        raise ProtocolValidationError("PLAN_NO_TOPIC", "规划缺少主题")
    goals_str = _field(r"学习目标[：:]\s*(.+)")
    goals = [g.strip() for g in goals_str.split("|") if g.strip()] if goals_str else []
    if not goals:
        raise ProtocolValidationError("PLAN_NO_GOALS", "规划缺少学习目标")
    difficulty = _field(r"目标难度[：:]\s*(.+)", "基础")
    weaknesses_str = _field(r"薄弱知识点[：:]\s*(.+)")
    weaknesses = [w.strip() for w in weaknesses_str.split("|") if w.strip()] if weaknesses_str else []
    style = _field(r"风格约束[：:]\s*(.+)")
    allow_str = _field(r"来源白名单[：:]\s*(.+)")
    allowlist = [a.strip() for a in allow_str.split("|") if a.strip()] if allow_str else []
    category_str = _field(r"学科类别[：:]\s*(.+)", "other")
    try:
        category = SubjectCategory(category_str)
    except ValueError:
        category = SubjectCategory.OTHER

    brief = ResourceBrief(
        topic=topic, learning_objectives=goals, target_difficulty=difficulty,
        weak_knowledge_points=weaknesses, style_constraints=style,
        source_allowlist=allowlist, subject_category=category,
    )
    validate_brief(brief)
    return brief


def validate_brief(brief: ResourceBrief) -> None:
    for field_name in ["topic", "target_difficulty"]:
        value = getattr(brief, field_name, "")
        if isinstance(value, str) and ("\\" in value or "/" in value):
            raise ProtocolValidationError("BRIEF_PATH_LEAK", f"field ''{field_name}'' contains path chars")
    for obj in brief.learning_objectives:
        if isinstance(obj, str):
            if "\\" in obj or "/" in obj:
                raise ProtocolValidationError("BRIEF_PATH_LEAK", "learning objective contains path chars")
            if "http://" in obj or "https://" in obj:
                raise ProtocolValidationError("BRIEF_URL_LEAK", "learning objective contains URL")
    for obj in brief.weak_knowledge_points:
        if isinstance(obj, str):
            if "\\" in obj or "/" in obj:
                raise ProtocolValidationError("BRIEF_PATH_LEAK", "weak knowledge point contains path chars")
            if "http://" in obj or "https://" in obj:
                raise ProtocolValidationError("BRIEF_URL_LEAK", "weak knowledge point contains URL")
    if isinstance(brief.style_constraints, str):
        if "\\" in brief.style_constraints or "/" in brief.style_constraints:
            raise ProtocolValidationError("BRIEF_PATH_LEAK", "style constraints contain path chars")
        if "http://" in brief.style_constraints or "https://" in brief.style_constraints:
            raise ProtocolValidationError("BRIEF_URL_LEAK", "style constraints contain URL")


def derive_requested_types(mode: str, single_type: ArtifactType | None = None) -> list[ArtifactType]:
    if mode == "single" and single_type is not None:
        return [single_type]
    return list(ArtifactType)
