from __future__ import annotations

import re
from dataclasses import dataclass, field

from backend.protocols.v2.models import ArtifactType


@dataclass
class SafetyResult:
    passed: bool
    issues: list[str] = field(default_factory=list)


# Dangerous content detection patterns
_DANGEROUS_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("PROMPT_INJECTION", re.compile(r"(忽略|无视|覆盖).{0,10}(提示|指令|系统|规则)", re.IGNORECASE)),
    ("ROLE_OVERRIDE", re.compile(r"(你现在是|你现在扮演|忘记你).{0,10}(不受限|无限制|任何角色)", re.IGNORECASE)),
    ("SQL_INJECTION", re.compile(r"\b(DROP\s+TABLE|DELETE\s+FROM|INSERT\s+INTO|ALTER\s+TABLE)\b", re.IGNORECASE)),
    ("XSS_SCRIPT", re.compile(r"<\s*script[\s>]", re.IGNORECASE)),
    ("XSS_ONERROR", re.compile(r"onerror\s*=", re.IGNORECASE)),
    ("CREDENTIAL_SEEK", re.compile(r"(API\s*密钥|api\s*key|密码是什么|你的密钥|你的密码)", re.IGNORECASE)),
    ("INSTRUCTION_EXECUTION", re.compile(r"(执行以下|运行这个|调用工具|访问文件)", re.IGNORECASE)),
]


def check_dangerous_content(text: str) -> SafetyResult:
    issues: list[str] = []
    for code, pattern in _DANGEROUS_PATTERNS:
        if pattern.search(text):
            issues.append(code)
    return SafetyResult(passed=len(issues) == 0, issues=issues)


# Citation allowlist sanitization
_CITATION_PATTERN = re.compile(r"\[资料(\d+)\]")


def sanitize_citation_allowlist(body: str, allowlist: list[str]) -> str:
    allow_set = set(allowlist)
    def _replace(match: re.Match[str]) -> str:
        ref = match.group(0)
        inner = f"资料{match.group(1)}"
        return ref if inner in allow_set else ""
    return _CITATION_PATTERN.sub(_replace, body)


# Type-specific quality gates
_COURSE_SECTIONS = ["学习目标", "核心概念", "逐步讲解", "常见误区", "个性化建议"]
_QB_LEVELS = ["基础", "提高", "挑战"]
_ADAPTIVE_SECTIONS = ["目标", "步骤", "验收标准", "参考方法"]

_MERMAID_SAFE_PREFIX = re.compile(r"^(flowchart|graph)\s", re.IGNORECASE)
_MERMAID_UNSAFE = re.compile(
    r"(click\s+.*href|javascript:|<script|onerror|onclick|style=|<iframe|<object|<embed)",
    re.IGNORECASE,
)


def validate_type_specific_gates(artifact_type: ArtifactType, body: str) -> SafetyResult:
    issues: list[str] = []

    if artifact_type == ArtifactType.COURSE_EXPLANATION:
        for section in _COURSE_SECTIONS:
            if f"## {section}" not in body:
                issues.append(f"MISSING_SECTION:{section}")

    elif artifact_type == ArtifactType.MIND_MAP:
        if not _MERMAID_SAFE_PREFIX.search(body):
            issues.append("MERMAID_UNSAFE_PREFIX")
        if _MERMAID_UNSAFE.search(body):
            issues.append("MERMAID_UNSAFE_CONTENT")
        if "<script" in body.lower() or "javascript:" in body.lower():
            issues.append("MERMAID_XSS")
        if "click " in body.lower() and "href" in body.lower():
            issues.append("MERMAID_CLICK_HANDLER")

    elif artifact_type == ArtifactType.QUESTION_BANK:
        for level in _QB_LEVELS:
            if f"## {level}" not in body:
                issues.append(f"MISSING_LEVEL:{level}")
        if "答案" not in body or "解析" not in body:
            issues.append("MISSING_ANSWER_OR_EXPLANATION")

    elif artifact_type == ArtifactType.EXTENDED_READING:
        # No hard requirements; source validation done via sanitize_citation_allowlist
        pass

    elif artifact_type == ArtifactType.ADAPTIVE_PRACTICE:
        for section in _ADAPTIVE_SECTIONS:
            if f"## {section}" not in body:
                issues.append(f"MISSING_ADAPTIVE_SECTION:{section}")

    return SafetyResult(passed=len(issues) == 0, issues=issues)
