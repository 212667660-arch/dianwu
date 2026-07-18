# S-022 五类资源生成 — Deepseek Write（思路·想法·潜在问题）

> 模型：Sol（DeepSeek v4 Pro）
> 日期：2026-07-16
> 关联设计：2026-07-16-five-resource-bundle-design.md
> 任务队列：S-022

---

## 一、对设计文档的理解与确认

### 1.1 核心架构决策

设计文档提出了一个清晰的新架构：

- **Planning Agent**：接收画像 + 学习进度 + 本地知识 + 公开来源 → 产出资源 Brief
- **五个 Specialist Agents**：各自独立生成一类资源（course_explanation / mind_map / question_bank / extended_reading / adaptive_practice）
- **Aggregator**：组装最终 bundle，计算状态（COMPLETED / PARTIAL / FAILED / CANCELLED）
- **新协议**：`learning-resource-bundle/v2`，旧 `learning-resource/v1` 保持不变

### 1.2 与旧实现的差异

| 维度 | 旧 v1 | 新 v2 |
|------|-------|-------|
| 资源类型 | 单一笔记+练习 | 五类独立资源 + 可选 bundle |
| 并发 | 无 | bundle 模式最多 2 个 specialist 并发 |
| 错误处理 | 整体失败 | 部分成功（PARTIAL），独立重试 |
| 取消 | 粗粒度 | 停止排队/运行中的 specialist，保留已完成 artifact |
| 质量 | 基础校验 | 五类独立质量门 + 安全门 |
| 前端渲染 | 纯文本 | 结构化卡片 + Mermaid 安全渲染 + 大纲回退 |

---

## 二、实施策略分析

### 2.1 设计文档强调的关键原则

> "现有资源生成逻辑集中在旧 v1 协议和 orchestrator.py，直接把五类并发流程继续堆进去会让取消、部分成功和重试难以验证。"

→ 必须创建**独立的资源包管线模块**，不往旧 orchestrator.py 里堆。

> "实施计划会新增独立的资源包管线模块，让现有编排器只负责会话状态和 SSE 转发"

→ 新模块职责清晰：接收 plan → 调度 specialists → 收集结果 → 产出 bundle。

> "数据库沿用幂等加列模式，前端拆成资源菜单、资源包和安全 Mermaid 三个小组件。"

→ 数据库：迁移脚本加列，不删旧列。
→ 前端：三个新组件（ResourceMenu / ResourceBundle / SafeMermaid），不推翻现有 UI。

### 2.2 我倾向的模块拆分

```
backend/
├── services/
│   ├── resource_bundle/          # 新模块（独立管线）
│   │   ├── __init__.py
│   │   ├── pipeline.py           # 管线入口：plan → dispatch → aggregate
│   │   ├── planner.py            # Planning Agent prompt + 调用
│   │   ├── specialists/          # 五个 Specialist Agent
│   │   │   ├── __init__.py
│   │   │   ├── base.py           # 公共基类 / 接口
│   │   │   ├── course_explanation.py
│   │   │   ├── mind_map.py
│   │   │   ├── question_bank.py
│   │   │   ├── extended_reading.py
│   │   │   └── adaptive_practice.py
│   │   ├── aggregator.py         # 组装 bundle + 状态计算
│   │   ├── safety.py             # 共享安全门 + 类型特定门
│   │   └── cancel.py             # 取消信号管理
│   ├── orchestrator.py           # 修改：只负责会话状态 + SSE 转发
├── protocols/
│   ├── v1/                       # 现有 v1 协议（不变）
│   ├── v2/                       # 新 v2 协议
│   │   ├── __init__.py
│   │   ├── models.py             # ResourceBundle, ResourceArtifact, Brief 等
│   │   ├── parser.py             # 解析 + 校验
│   │   └── sse.py                # SSE 事件构造
├── models/
│   ├── schemas.py                # 加列：bundle 相关字段
├── routers/
│   ├── resource.py               # 新增 v2 端点
```

### 2.3 前端拆分策略

```
src/components/learning/
├── ResourceMenu.vue              # 资源类型选择菜单（bundle/single）
├── ResourceBundle.vue            # 资源包结果展示容器
├── ResourceCard.vue              # 单个资源卡片（expand/collapse/copy/retry）
├── SafeMermaid.vue               # 安全 Mermaid 渲染 + 大纲回退
```

---

## 三、潜在问题与风险

### 3.1 高风险

**【P0】并发 specialist 的取消信号传播**
- 问题：当前 orchestrator 用全局字典 `_generation_cancel_events` 管理取消。新管线需要在并发场景下正确传播取消到正在运行的 2 个 specialist 以及排队中的其余 specialist。
- 缓解：`cancel.py` 设计为 per-bundle 的取消信号，所有 specialist 共享同一个 `asyncio.Event`。

**【P0】部分成功下的数据库一致性**
- 问题：PARTIAL 状态的 bundle 需要在数据库中同时存储成功 artifact 和失败的错误码，且后续重试时要能定位到具体失败的 specialist。
- 缓解：每个 artifact 独立行存储，带 `bundle_id` 外键 + `status` 字段。重试时按 artifact_id 覆盖。

**【P0】模型中断（interruption）时的 artifact 隔离**
- 问题：设计文档明确要求 "模型中断绝不静默拼接两个画像的输出"。当前 llm_service 把错误转成文本返回 200，可能在中断时返回不完整输出。
- 缓解：v2 管线需要在 specialist 调用外层加 try/except，捕获中断后标记该 artifact 为 safe error，不影响已完成的 artifact。

### 3.2 中风险

**【P1】Mermaid 安全渲染的前端实现**
- 问题：设计文档要求 "只接受 flowchart 或 graph，拒绝 HTML/script/click handler"。前端 Mermaid 库可能接受不安全的输入。
- 缓解：前端解析前做正则白名单过滤，只放行 `flowchart` 和 `graph` 前缀；服务端同样做过滤，双重防护。

**【P1】extended_reading 的来源引用校验**
- 问题：设计文档要求 "只能引用已提供的 source ID" 和 "无外部来源时明确声明"。这需要在前端展示时关联 source snapshots。
- 缓解：在 aggregator 中做 source ID 白名单校验，不合格的引用替换为 "[来源暂不可用]"。

**【P1】adaptive_practice 的学科自适应分类**
- 问题：计算机学科生成 code lab（需 starter code），其他学科生成 experiment/case analysis。分类逻辑依赖 planning agent 的 subject_category 输出。
- 缓解：planning brief 中要求明确的 subject_category 字段枚举值，后端校验后再路由到对应 specialist prompt。

### 3.3 低风险

**【P2】v1 兼容性**
- 问题：设计文档要求历史 v1 消息继续渲染为文本。数据库中 v1 资源的字段可能和新 v2 字段不兼容。
- 缓解：迁移脚本只加列不删列，v1 资源读路径不变。

**【P2】前端卡片在窄屏的布局**
- 问题：设计文档要求 "窄屏一列垂直排列，控件换行无水平滚动"。
- 缓解：用 CSS flexbox + media query，现有的响应式基础设施应该足够。

---

## 四、TDD 实施顺序建议

按照设计文档的测试策略，建议以下顺序：

### Phase 1：协议与模型层（无外部依赖）
1. v2 协议 models（ResourceBundle, ResourceArtifact, ResourceBrief）
2. v2 协议 parser（解析 + 枚举拒绝 + v1 兼容）
3. 数据库迁移（加列 + 回滚测试）
4. 共享安全门（危险内容、来源白名单、类型特定门）

### Phase 2：管线核心（mock 模型调用）
5. Planning Agent（prompt 构建 + brief 解析 + 失败处理）
6. 五个 Specialist Agent prompt 构建器
7. Pipeline 调度（bundle/single 模式 + 并发控制）
8. Aggregator（组装 + 状态计算 + 排序）
9. 取消信号传播

### Phase 3：SSE 与 HTTP 集成
10. v2 SSE 事件（resource_plan / resource_progress / resource_artifact / resource_bundle）
11. v2 HTTP 端点（请求校验 + IPC 字段白名单）
12. orchestrator 修改（会话状态 + SSE 转发，不侵入管线）

### Phase 4：前端
13. ResourceMenu（composer 中的类型选择）
14. ResourceBundle + ResourceCard（结果展示 + expand/collapse/copy/retry）
15. SafeMermaid（安全渲染 + 大纲回退）

### Phase 5：集成验证
16. 端到端 bundle 流程（mock LLM）
17. 端到端 single 流程
18. 部分成功 + 重试
19. 取消 + 断开
20. v1 兼容回归

---

## 五、需要确认的未决问题

1. **模型配置**：当前使用 DeepSeek v4 Pro。Planning Agent 和五个 Specialist Agent 是否需要不同的模型配置（如某些用更轻量的模型）？设计文档未明确。
   → 暂定：全部使用同一个模型配置，后续可通过 model_runtime_router 切换。

2. **前端 IPC 字段白名单**：设计文档说 "Renderer 不能提供 model profiles、backend addresses、tokens、file paths"。当前 Electron preload 是否已有对应校验？
   → 需检查现有 IPC 校验逻辑，可能需要新增 resource_mode / resource_type 的字段白名单。

3. **bundle 的持久化时机**：设计文档说 SSE 事件 `resource_bundle` 是最终 bundle。何时写入数据库？每个 artifact 完成时即时写还是全部完成后批量写？
   → 建议：每个 artifact 完成时即时写（支持取消后保留已完成 artifact），bundle 完成时更新状态。

---

*本文档随实施推进持续更新。新发现的问题或思路变化将追加到对应章节。*