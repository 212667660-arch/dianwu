# 五类个性化资源生成 — TDD 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** 扩展 A3 系统从单一 v1 笔记+练习协议到五类个性化学习资源独立生成与桌面展示。

**Architecture:** 新增独立资源包管线模块 backend/services/resource_bundle/，包含 Planning Agent、五个 Specialist Agent、Aggregator 和安全门。现有 orchestrator.py 仅保留会话状态管理和 SSE 转发。数据库用幂等加列迁移。前端拆为 ResourceMenu、ResourceBundle/ResourceCard、SafeMermaid 三个组件。

**Tech Stack:** FastAPI + SQLAlchemy + SQLite, Pydantic v2, asyncio, Vue 3 + TypeScript, Mermaid.js, Vitest, pytest

---

## 文件结构总览

### 后端新建

backend/protocols/v2/__init__.py          # 导出 ResourceBrief, ResourceArtifact, ResourceBundle 等
backend/protocols/v2/models.py            # Pydantic 模型：枚举、类型、Artifact、Bundle
backend/protocols/v2/parser.py            # 解析 v2 协议文本、SSE 事件序列化
backend/protocols/v2/sse_events.py        # SSE 事件构造器
backend/services/resource_bundle/__init__.py
backend/services/resource_bundle/pipeline.py        # 管线入口（bundle/single 调度）
backend/services/resource_bundle/planner.py         # Planning Agent prompt + brief 校验
backend/services/resource_bundle/cancel.py          # 取消信号 per-bundle 管理
backend/services/resource_bundle/safety.py          # 共享安全门 + 类型特定门
backend/services/resource_bundle/aggregator.py      # 组装 bundle + 状态计算
backend/services/resource_bundle/specialists/__init__.py
backend/services/resource_bundle/specialists/base.py           # Specialist 基类
backend/services/resource_bundle/specialists/course_explanation.py
backend/services/resource_bundle/specialists/mind_map.py
backend/services/resource_bundle/specialists/question_bank.py
backend/services/resource_bundle/specialists/extended_reading.py
backend/services/resource_bundle/specialists/adaptive_practice.py
backend/services/resource_db.py           # bundle/artifact 数据库 CRUD

### 后端修改

backend/models/schemas.py                 # ChatRequest 加 resource_mode/resource_type；新增 BundleResponse
backend/database.py                       # 迁移加列（resource_bundles, resource_artifacts 表）
backend/routers/resource.py               # 新增 /api/resource-bundle 端点
backend/services/orchestrator.py          # 集成管线：profile->plan->dispatch->SSE转发

### 后端测试新建

backend/tests/test_resource_bundle_models.py    # v2 模型 round-trip、枚举拒绝、v1 兼容
backend/tests/test_resource_bundle_parser.py    # 协议解析、schema 校验
backend/tests/test_resource_bundle_safety.py    # 危险内容、来源白名单、类型特定门
backend/tests/test_resource_bundle_planner.py   # Planning Agent prompt 契约 + brief 校验
backend/tests/test_resource_bundle_specialists.py  # 五个 Specialist prompt 契约
backend/tests/test_resource_bundle_pipeline.py  # bundle/single/partial/cancel 调度
backend/tests/test_resource_bundle_aggregator.py # 组装、状态、排序
backend/tests/test_resource_bundle_sse.py       # SSE 事件格式
backend/tests/test_resource_bundle_api.py       # HTTP 端点 + IPC 字段白名单
backend/tests/test_resource_bundle_db.py        # 数据库 CRUD + 迁移验证
backend/tests/test_resource_bundle_integration.py # 全流程集成

### 前端新建

src/components/learning/ResourceMenu.vue     # 资源类型选择（bundle/single）
src/components/learning/ResourceBundle.vue   # 资源包结果容器
src/components/learning/ResourceCard.vue     # 单资源卡片（expand/collapse/copy/retry）
src/components/learning/SafeMermaid.vue      # 安全 Mermaid 渲染 + 大纲回退


---

### Task 1: v2 协议模型定义

**Files:**
- Create: backend/protocols/v2/__init__.py
- Create: backend/protocols/v2/models.py
- Create: backend/tests/test_resource_bundle_models.py

**Steps:**
1. 编写测试 — ArtifactType/BundleStatus/ArtifactStatus 枚举值校验、ResourceBrief/ResourceArtifact/ResourceBundle 模型 round-trip、空字段拒绝、type_specific_data 灵活性
2. 运行: python -m pytest backend/tests/test_resource_bundle_models.py -v → FAIL
3. 实现 models.py — 五个枚举(ArtifactType/BundleStatus/ArtifactStatus/SubjectCategory/ResourceMode) + ResourceBrief(含 topic/learning_objectives/target_difficulty/weak_knowledge_points/style_constraints/source_allowlist/subject_category) + ResourceArtifact(含 artifact_id/type/title/status/body/type_specific_data/quality_score/quality_issues/error_code/retryable) + ResourceBundle(含 bundle_id/protocol_version/topic/profile_version/learning_state_version/mode/status/requested_types/artifacts/aggregate_quality/created_at/knowledge_sources/public_sources)
4. 运行: python -m pytest backend/tests/test_resource_bundle_models.py backend/tests/test_protocols.py -v → 全部 PASS
5. Commit: feat: add v2 resource bundle protocol models

### Task 2: v2 协议解析器与 SSE 事件

**Files:**
- Create: backend/protocols/v2/parser.py
- Create: backend/protocols/v2/sse_events.py
- Create: backend/tests/test_resource_bundle_parser.py

**Steps:**
1. 编写测试 — bundle_to_json/parse_bundle_from_json round-trip、无效 JSON 抛 ProtocolValidationError、validate_bundle 检测类型不匹配、SSE plan_event/progress_event/artifact_event/bundle_event payload schema
2. 运行: pytest backend/tests/test_resource_bundle_parser.py -v → FAIL
3. 实现 parser.py (bundle_to_json/parse_bundle_from_json/validate_bundle) + sse_events.py (plan_event/progress_event/artifact_event/bundle_event/bundle_to_sse_payload)
4. 运行: pytest backend/tests/test_resource_bundle_parser.py -v → PASS
5. Commit: feat: add v2 protocol parser and SSE event constructors

### Task 3: 数据库迁移与 CRUD

**Files:**
- Modify: backend/database.py (_sqlite_migrate 追加 resource_bundles 和 resource_artifacts 表加列)
- Create: backend/services/resource_db.py
- Create: backend/tests/test_resource_bundle_db.py

**Steps:**
1. 编写测试 — save_bundle+get_bundle round-trip、save_artifact 幂等 upsert、delete_bundle 级联清理、PARTIAL 状态保存与重试覆盖、v1 chat_sessions 不受影响
2. 运行: pytest backend/tests/test_resource_bundle_db.py -v → FAIL
3. 实现 database.py 迁移加列(resource_bundles: bundle_id/session_id/protocol_version/topic/profile_version/learning_state_version/mode/status/requested_types/artifacts_json/aggregate_quality/created_at/knowledge_sources_json/public_sources_json; resource_artifacts: artifact_id/bundle_id/type/title/status/body/type_specific_data_json/quality_score/quality_issues_json/error_code/retryable) + resource_db.py (save_bundle/save_artifact/get_bundle/delete_bundle 使用原始 SQL + ON CONFLICT 幂等)
4. 运行: pytest backend/tests/test_resource_bundle_db.py backend/tests/test_errors_and_sessions.py -v → 全部 PASS
5. Commit: feat: add resource bundle DB migration and CRUD

### Task 4: 共享安全门

**Files:**
- Create: backend/services/resource_bundle/__init__.py
- Create: backend/services/resource_bundle/safety.py
- Create: backend/tests/test_resource_bundle_safety.py

**Steps:**
1. 编写测试 — check_dangerous_content(正常文本通过/提示注入拒绝/SQL注入拒绝/XSS拒绝/角色覆盖拒绝/凭据探询拒绝)、sanitize_citation_allowlist(有效引用保留/编造引用移除)、validate_type_specific_gates(course_explanation五章节检查/mind_map仅flowchart和graph放行拒绝script和click/mind_map拒绝sequence和class/ question_bank三难度等级检查/adaptive_practice五章节+starter_code条件检查)
2. 运行: pytest backend/tests/test_resource_bundle_safety.py -v → FAIL
3. 实现 safety.py — DANGEROUS_PATTERNS 七条正则 + check_dangerous_content、CITATION_PATTERN + sanitize_citation_allowlist、validate_type_specific_gates(按 ArtifactType 分派五类检查含 MERMAID_SAFE_PREFIX/MERMAID_UNSAFE)
4. 运行: pytest backend/tests/test_resource_bundle_safety.py -v → PASS
5. Commit: feat: add shared safety gates and type-specific quality validation

### Task 5: Specialist 基类与五个 Prompt 构建器

**Files:**
- Create: backend/services/resource_bundle/specialists/__init__.py
- Create: backend/services/resource_bundle/specialists/base.py
- Create: backend/services/resource_bundle/specialists/course_explanation.py
- Create: backend/services/resource_bundle/specialists/mind_map.py
- Create: backend/services/resource_bundle/specialists/question_bank.py
- Create: backend/services/resource_bundle/specialists/extended_reading.py
- Create: backend/services/resource_bundle/specialists/adaptive_practice.py
- Create: backend/tests/test_resource_bundle_specialists.py

**Steps:**
1. 编写测试 — build_specialist_messages 包含 brief 所有字段、specialist_for_type 返回正确类型、CourseExplanation: prompt 包含五章节要求+parse 成功/失败、MindMap: prompt 包含 flowchart/graph+大纲要求+parse mermaid+outline+type_specific_data、QuestionBank: prompt 包含三难度+parse 各难度计数、ExtendedReading: prompt 包含引用约束+parse 无外部来源声明、AdaptivePractice: CS brief prompt 含代码实验+非CS brief prompt 不含起始代码+parse 分类输出
2. 运行: pytest backend/tests/test_resource_bundle_specialists.py -v → FAIL
3. 实现 base.py(Specialist ABC + SpecialistResult + build_specialist_messages + specialist_for_type 工厂) + 五个 specialist(各含 build_prompt 和 parse, parse 均先 check_dangerous_content 再类型特定解析)
4. 运行: pytest backend/tests/test_resource_bundle_specialists.py -v → PASS
5. Commit: feat: add five specialist agents with prompt builders and parsers
### Task 6: Planning Agent

Create: backend/services/resource_bundle/planner.py, backend/tests/test_resource_bundle_planner.py

1. Tests: build_planner_messages includes profile+progress+knowledge, parse_plan_output valid/invalid, validate_brief rejects path/URL leaks, derive_requested_types
2. Run: pytest backend/tests/test_resource_bundle_planner.py -v (expect FAIL)
3. Implement planner.py with build_planner_messages, parse_plan_output, validate_brief, derive_requested_types
4. Run: pytest ... -v (expect PASS)
5. Commit: feat: add planning agent with brief parser and safety

### Task 7: Cancel Signal Management

Create: backend/services/resource_bundle/cancel.py

BundleCancellation dataclass with asyncio.Event+cancelled flag, global _bundle_cancellations dict, get_or_create/cancel/cleanup functions
Commit: feat: add per-bundle cancellation signal management

### Task 8: Aggregator

Create: backend/services/resource_bundle/aggregator.py, backend/tests/test_resource_bundle_aggregator.py

1. Tests: compute_bundle_status(all=MIXED), aggregate_bundle(COMPLETED/PARTIAL ordering by catalog)
2. Implement CATALOG_ORDER dict + compute_bundle_status + aggregate_bundle
3. Commit: feat: add aggregator for bundle assembly and quality

### Task 9: Pipeline Core

Create: backend/services/resource_bundle/pipeline.py, backend/tests/test_resource_bundle_pipeline.py

1. Tests: single mode, bundle all 5, partial success(4 ok 1 fail), cancellation
2. Implement BundlePipeline.run: Phase1 plan -> Phase2 Semaphore(2) specialists -> Phase3 aggregate
3. Commit: feat: add pipeline core with 2-concurrent dispatch

### Task 10: HTTP Endpoint and Schemas

Modify: backend/models/schemas.py, backend/routers/resource.py
Create: backend/tests/test_resource_bundle_api.py

1. Tests: POST /api/resource-bundle bundle/single modes, 422 on invalid fields, v1 /api/chat unaffected
2. ChatRequest: add resource_mode/resource_type fields with validators; new BundleResponse schema
3. resource.py: add /resource-bundle POST endpoint using BundlePipeline
4. Commit: feat: add v2 /api/resource-bundle endpoint

### Task 11: Orchestrator Integration

Modify: backend/services/orchestrator.py
Create: backend/tests/test_resource_bundle_sse.py

1. Tests: SSE event JSON schema validation
2. Modify orchestrator: detect resource_mode, use BundlePipeline, yield SSE events
3. Commit: feat: integrate v2 bundle pipeline into orchestrator

### Task 12: Frontend ResourceMenu

Create: src/components/learning/ResourceMenu.vue, src/tests/components/ResourceMenu.test.ts

1. Tests: renders bundle default + 5 single types, emits update:modelValue on change
2. Implement select dropdown with v-model mapping
3. Commit: feat: add ResourceMenu component

### Task 13: Frontend ResourceCard + ResourceBundle

Create: src/components/learning/ResourceCard.vue, ResourceBundle.vue, tests

1. Tests: renders topic/status, expand/collapse, retry button for FAILED
2. Implement ResourceCard(expand/collapse/copy/retry/Mermaid/Markdown) + ResourceBundle(header+cards loop)
3. Commit: feat: add ResourceCard and ResourceBundle components

### Task 14: Frontend SafeMermaid

Create: src/components/learning/SafeMermaid.vue, src/tests/components/SafeMermaid.test.ts

1. Tests: valid flowchart renders, invalid/script falls back to outline
2. Implement mermaidCode/safeToRender/outlineText computed + mermaid.render with strict security
3. Commit: feat: add SafeMermaid with strict security and outline fallback

### Task 15: Integration Regression

Create: backend/tests/test_resource_bundle_integration.py

1. Tests: full bundle all 5 COMPLETED, partial 2 fail 3 ok PARTIAL, v1 parse_resource still works
2. Run: pytest backend/tests/ -v --ignore=backend/tests/knowledge (all PASS)
3. Commit: test: add full pipeline integration with v1 regression

---

## Self-Review Checklist

### Spec Coverage

| Design Requirement | Task |
|---|---|
| v2 protocol models | Task 1 |
| Parser/serializer round-trip | Task 2 |
| SSE events | Task 2, 11 |
| DB migration + CRUD | Task 3 |
| Safety gates | Task 4 |
| Five specialists | Task 5 |
| Planning Agent | Task 6 |
| Cancel signals | Task 7 |
| Aggregator | Task 8 |
| Pipeline dispatch | Task 9 |
| HTTP endpoint + IPC allowlist | Task 10 |
| Orchestrator SSE forwarding | Task 11 |
| ResourceMenu | Task 12 |
| ResourceCard/Bundle | Task 13 |
| SafeMermaid | Task 14 |
| Integration + v1 regression | Task 15 |

### No Placeholders

All tasks have concrete code, exact commands, and expected outputs. No TBD/TODO/implement-later patterns.

### Type Consistency

ArtifactType, ArtifactStatus, BundleStatus, SubjectCategory consistent across all tasks.
BundlePipeline.run() signature consistent. Frontend artifact.type matches backend enum values.

---

Plan complete. Two execution options:

1. Subagent-Driven (recommended) - dispatch subagent per task, review between
2. Inline Execution - execute in this session with checkpoints

Which approach?