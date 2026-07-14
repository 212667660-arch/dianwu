"""
agent_skills.py — 画像 Agent 所需的核心技能函数

设计：每个函数内部构造详细提示词，调用 services.llm_service.llm_call(prompt)
返回结果。所有通信采用带标记的纯文本，不使用复杂 JSON 嵌套。
"""
from services.llm_service import llm_call


def skill_structured_summary(conversation_text: str, instruction: str) -> str:
    """将多轮对话总结为固定格式的学习者画像文本。

    参数:
        conversation_text: 多轮对话合并后的全文（各轮用换行分隔）。
        instruction: 希望的总结结构说明（如画像字段要求）。
    返回:
        以 `【学习者画像】` 开头的文本，包含以下字段（字段缺失填“未明确”）：
        年级 / 学科 / 当前水平 / 薄弱知识点 / 学习风格偏好 / 学习目标。
        示例：
            【学习者画像】
            年级：初二
            学科：数学
            当前水平：理解
            薄弱知识点：一次函数图像
            学习风格偏好：视觉型
            学习目标：能独立画出函数图像并解题
    """
    prompt = f"""你是一个教育多智能体系统的「对话摘要器」。
请把下面的多轮对话，严格按指定结构总结为「带标记的纯文本」。
必须使用如下字段与格式（字段名带【】或冒号标记），信息缺失时填“未明确”，不要编造：
【学习者画像】
年级：
学科：
当前水平：
薄弱知识点：
学习风格偏好：
学习目标：

总结结构要求：
{instruction}

对话全文：
{conversation_text}

请仅输出画像文本："""
    return llm_call(prompt).strip()


def skill_learning_style_inference(statements: str) -> str:
    """从学生对自己学习方式的描述中，推断学习风格。

    参数:
        statements: 学生关于自身学习方式的自我描述文本。
    返回:
        格式：`学习风格偏好：<风格>（<简短解释>）`。
        可选风格：视觉型、听觉型、动觉型、读写型（可指出主导）。
        示例：`学习风格偏好：视觉型（喜欢看图表和动画）`
    """
    prompt = f"""你是学习风格分析专家。请依据学生对自身学习方式的表述，推断其主导学习风格。
可选风格：视觉型、听觉型、动觉型、读写型。可给出复合型，但需指出主导。
输出格式：`学习风格偏好：<风格>（<简短解释>）`，只输出这一行。

学生表述：
{statements}

请输出："""
    return llm_call(prompt).strip()


def skill_weakness_miner(vague_problem: str) -> str:
    """从模糊问题描述中，挖掘出具体、规范的薄弱知识点列表。

    参数:
        vague_problem: 学生对困难的模糊描述（如“我函数总是错”）。
    返回:
        格式：`薄弱知识点：<知识点1>，<知识点2>，...`。
        知识点表述要具体、规范（如“一次函数图像”“待定系数法”）。
        示例：`薄弱知识点：一次函数图像，待定系数法`
    """
    prompt = f"""你是学科薄弱点诊断专家。请把学生模糊的问题描述，转化为具体、规范的知识点列表。
知识点表述要具体（如“一次函数图像”“待定系数法”），避免笼统。
输出格式：`薄弱知识点：<知识点1>，<知识点2>，...`，只输出这一行。

学生模糊描述：
{vague_problem}

请输出："""
    return llm_call(prompt).strip()


def skill_topic_extractor(profile_text: str, request_message: str) -> str:
    """从用户请求中提取本次要生成资源的知识点 / 主题。

    参数:
        profile_text: 学习者画像文本（提供学科与薄弱点上下文）。
        request_message: 用户的具体请求（如“给我一次函数学习笔记和练习”）。
    返回:
        一个简短的知识点名称（如“一次函数”“勾股定理”），无多余解释。
    """
    prompt = f"""你是教育系统的「请求解析器」。请从学生的一句话请求里，提取他本次想学习的具体知识点/主题。
只输出知识点名称本身（如：一次函数、勾股定理、英语定语从句），不要输出句子，不要加标点解释。

学习者画像（供参考学科背景）：
{profile_text}

学生请求：
{request_message}

请仅输出知识点名称："""
    return llm_call(prompt).strip()


def skill_note_generator(profile_text: str, topic: str, style_notes: str) -> str:
    """根据画像、知识点、风格要求生成个性化学习笔记。

    参数:
        profile_text: 学习者画像文本。
        topic: 知识点名称。
        style_notes: 风格要求（如“用图表辅助、语言通俗”）；可空。
    返回:
        以 `【学习笔记】` 开头的笔记文本，结构化为若干要点。
    """
    style_block = f"\n风格要求：{style_notes}\n" if style_notes else ""
    prompt = f"""你是一个「个性化学习笔记生成器」。请基于学习者画像和指定知识点，生成一份结构清晰、易懂的学习笔记。
要求：
1. 第一行必须是 `【学习笔记】<知识点名称>`。
2. 之后用「一、 二、 三、……」分条组织核心概念、要点、易错提醒。
3. 语言贴合学习者的水平和风格（见画像与风格要求），避免照抄教科书。
4. 不要使用复杂 JSON，纯文本 + 编号即可。
5. 严格使用【】标记，不要遗漏。

学习者画像：
{profile_text}
{style_block}
知识点：{topic}

示例输出：
【学习笔记】一次函数
一、定义：形如 y=kx+b（k≠0）的函数
二、图像：一条直线，k 决定倾斜方向
三、易错：k=0 时不是一次函数

请仅输出笔记文本："""
    return llm_call(prompt).strip()


def skill_question_composer(profile_text: str, topic: str, difficulty_levels: str) -> str:
    """根据画像、知识点、难度层次生成配套练习题。

    参数:
        profile_text: 学习者画像文本。
        topic: 知识点名称。
        difficulty_levels: 难度层次说明（如“基础+提高”）；可空，默认基础+提高。
    返回:
        以 `【配套练习】` 开头的题目文本，每题含 题目/答案/解析。
    """
    diff_block = f"\n难度层次：{difficulty_levels}\n" if difficulty_levels else "\n难度层次：基础 + 提高\n"
    prompt = f"""你是一个「分层练习题出题器」。请基于学习者画像和指定知识点，出一组配套练习。
要求：
1. 第一行必须是 `【配套练习】`。
2. 每题格式严格如下（题目编号从1开始）：
题目1（基础）：<题干>
答案：<答案>
解析：<解析>
题目2（提高）：<题干>
答案：<答案>
解析：<解析>
3. 题目要对应学习者薄弱点，难度按层次递进，解析要讲清思路。
4. 严格使用【】标记，不要遗漏任何字段。

学习者画像：
{profile_text}
知识点：{topic}{diff_block}
示例输出：
【配套练习】
题目1（基础）：求 y=2x+1 与 x 轴交点
答案：( -1/2, 0 )
解析：令 y=0，解 2x+1=0 得 x=-1/2
题目2（提高）：已知一次函数过(1,3)(2,5)，求解析式
答案：y=2x+1
解析：设 y=kx+b，代入两点得方程组求解

请仅输出练习文本："""
    return llm_call(prompt).strip()
