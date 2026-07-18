# Five-Resource Bundle Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将现有五类资源模块从孤立骨架修复为桌面端可触发、按画像和学习状态生成、可取消、可部分成功、可持久化恢复并可独立重试的完整闭环。

**Architecture:** 保留 `backend/services/resource_bundle/`、五个 Specialist 和 `learning-resource-bundle/v2`，新增统一 `ResourceBundleService` 作为会话、知识、来源、状态和仓储边界。普通 HTTP 与 SSE 共用该服务；Pipeline 只负责规划、最多两个并发生成、取消和事件回调。前端使用严格 TypeScript 契约、`SafeMarkdown`、`SafeMermaid` 与结构化 bundle 状态，不再把模型正文作为 HTML。

**Tech Stack:** FastAPI, SQLAlchemy, SQLite, Pydantic v2, asyncio, Vue 3, TypeScript, Electron IPC, Vitest, pytest

---

## File Structure

### Backend create

- `backend/services/resource_bundle/service.py` — 会话上下文、缓存隔离、Pipeline 调用、状态恢复、持久化和单 artifact 重试。
- `backend/tests/test_resource_bundle_service.py` — 服务层状态、上下文、持久化、失败和重试测试。
- `backend/tests/test_resource_bundle_orchestrator_integration.py` — 普通与 SSE 端到端事件、取消和历史恢复。

### Backend modify

- `backend/protocols/v2/models.py` — 严格模式、协议版本、跨字段不变量和可选安全元数据。
- `backend/protocols/v2/parser.py` — 解析时执行 bundle 跨字段校验。
- `backend/services/resource_bundle/planner.py` — 逐行解析、服务器来源白名单交集和严格枚举。
- `backend/services/resource_bundle/safety.py` — 只保留结构安全；类型完整性移至质量门并在生产路径调用。
- `backend/services/resource_bundle/specialists/*.py` — 使用统一静态 system prompt、严格五类解析和稳定错误码。
- `backend/services/resource_bundle/pipeline.py` — 事件回调、共享取消、运行中任务取消、逐 artifact 回调和 `finally` 清理。
- `backend/services/resource_bundle/cancel.py` — 生成 ID 与 bundle ID 共享取消对象。
- `backend/services/resource_bundle/aggregator.py` — 按 requested types 计算状态，只聚合成功资源质量。
- `backend/services/resource_db.py` — session-scoped bundle/artifact CRUD、列表、读取和重试覆盖。
- `backend/database.py` — 幂等索引、会话归属和旧表补列。
- `backend/services/db.py` — 删除会话时清理 bundle；新增 bundle 后恢复稳定状态。
- `backend/models/schemas.py` — 严格请求、响应和 bundle schema。
- `backend/routers/resource.py` — 复用统一服务，移除空画像和硬编码版本。
- `backend/services/orchestrator.py` — 只负责会话锁和 SSE 转发，不复制 bundle 业务逻辑。
- `backend/routers/sessions.py` — 历史响应加入当前会话 bundle。

### Frontend create

- `a3-front/a3-front/src/components/learning/SafeMarkdown.vue` — 无 `v-html` 的受限 Markdown token 渲染。
- `a3-front/a3-front/src/tests/components/SafeMarkdown.test.ts` — HTML/XSS、标题、列表和代码块测试。

### Frontend modify

- `a3-front/a3-front/src/api/types.ts` — ResourceBundle、ResourceArtifact、ResourceSelection 和判别联合 SSE 类型。
- `a3-front/a3-front/src/api/backend.ts` — chat/stream 资源选项与 artifact retry。
- `a3-front/a3-front/electron/ipc-contract.mjs` — chat body 固定字段校验。
- `a3-front/a3-front/electron/ipc-contract.test.mjs` — bundle/single/retry 参数白名单测试。
- `a3-front/a3-front/src/components/learning/ResourceMenu.vue` — 严格 selection 类型和禁用状态。
- `a3-front/a3-front/src/components/learning/ResourceBundle.vue` — typed props、进度和 retry loading。
- `a3-front/a3-front/src/components/learning/ResourceCard.vue` — SafeMarkdown、SafeMermaid、失败正文不可复制。
- `a3-front/a3-front/src/components/learning/SafeMermaid.vue` — 响应式渲染失败回退、唯一 ID、规模限制。
- `a3-front/a3-front/src/views/SmartTutor.vue` — composer selector、SSE bundle 事件、历史 bundle 和 retry。
- `a3-front/a3-front/src/views/SmartTutor.test.ts` — 真正的桌面入口集成测试。
- `a3-front/a3-front/src/stores/backend.ts` — 会话历史 bundle 类型和刷新。

---

### Task 1: Strict v2 protocol and planner parsing

**Files:**
- Modify: `backend/protocols/v2/models.py`
- Modify: `backend/protocols/v2/parser.py`
- Modify: `backend/services/resource_bundle/planner.py`
- Test: `backend/tests/test_resource_bundle_models.py`
- Test: `backend/tests/test_resource_bundle_parser.py`
- Test: `backend/tests/test_resource_bundle_planner.py`

- [ ] **Step 1: Write failing model and planner regression tests**

```python
def test_plan_empty_optional_lines_remain_empty():
    brief = parse_plan_output(PLAN_WITH_EMPTY_OPTIONAL_LINES, source_allowlist=[])
    assert brief.weak_knowledge_points == []
    assert brief.style_constraints == ""
    assert brief.source_allowlist == []


def test_plan_sources_are_intersected_with_server_allowlist():
    brief = parse_plan_output(PLAN_WITH_SOURCES_1_AND_99, source_allowlist=["资料1"])
    assert brief.source_allowlist == ["资料1"]


def test_bundle_rejects_requested_artifact_type_mismatch():
    with pytest.raises(ValidationError):
        make_bundle(
            requested_types=[ArtifactType.COURSE_EXPLANATION],
            artifacts=[make_artifact(ArtifactType.MIND_MAP)],
        )
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/test_resource_bundle_models.py backend/tests/test_resource_bundle_parser.py backend/tests/test_resource_bundle_planner.py -q
```

Expected: planner optional fields contain the next labels, fabricated source IDs survive, and mismatched bundle construction does not fail.

- [ ] **Step 3: Implement strict line parsing and model invariants**

Use exact field-line parsing:

```python
_PLAN_LINE = re.compile(r"^(主题|学习目标|目标难度|薄弱知识点|风格约束|来源白名单|学科类别)[：:]\s*(.*)$")


def _plan_fields(raw: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in raw.splitlines():
        match = _PLAN_LINE.fullmatch(line.strip())
        if match:
            fields[match.group(1)] = match.group(2).strip()
    return fields


def parse_plan_output(raw: str, source_allowlist: list[str]) -> ResourceBrief:
    fields = _plan_fields(raw)
    supplied = [item for item in fields.get("来源白名单", "").split("|") if item]
    trusted = [item for item in supplied if item in set(source_allowlist)]
    return ResourceBrief(
        topic=fields["主题"],
        learning_objectives=_split_required(fields.get("学习目标", ""), "PLAN_NO_GOALS"),
        target_difficulty=TargetDifficulty(fields.get("目标难度", "基础")),
        weak_knowledge_points=_split_optional(fields.get("薄弱知识点", "")),
        style_constraints=fields.get("风格约束", ""),
        source_allowlist=trusted,
        subject_category=SubjectCategory(fields.get("学科类别", "other")),
    )
```

Add `ResourceMode`, `TargetDifficulty`, `Literal["learning-resource-bundle/v2"]`, unique requested types, unique artifact types, and exact requested/artifact set validation using `@model_validator(mode="after")`.

- [ ] **Step 4: Run tests and verify GREEN**

Run the Step 2 command. Expected: all pass.

- [ ] **Step 5: Commit**

```powershell
git add backend/protocols/v2/models.py backend/protocols/v2/parser.py backend/services/resource_bundle/planner.py backend/tests/test_resource_bundle_models.py backend/tests/test_resource_bundle_parser.py backend/tests/test_resource_bundle_planner.py
git commit -m "fix: enforce v2 resource protocol invariants"
```

### Task 2: Enforce all five specialist quality contracts

**Files:**
- Modify: `backend/services/resource_bundle/specialists/base.py`
- Modify: `backend/services/resource_bundle/specialists/course_explanation.py`
- Modify: `backend/services/resource_bundle/specialists/mind_map.py`
- Modify: `backend/services/resource_bundle/specialists/question_bank.py`
- Modify: `backend/services/resource_bundle/specialists/extended_reading.py`
- Modify: `backend/services/resource_bundle/specialists/adaptive_practice.py`
- Modify: `backend/services/resource_bundle/safety.py`
- Test: `backend/tests/test_resource_bundle_specialists.py`
- Test: `backend/tests/test_resource_bundle_safety.py`

- [ ] **Step 1: Write failing strict-gate tests**

```python
@pytest.mark.parametrize("missing", COURSE_SECTIONS)
def test_course_requires_every_section(missing):
    output = complete_course_output().replace(f"## {missing}\n内容", "")
    assert CourseExplanationSpecialist().parse(output, "a1").artifact.status == ArtifactStatus.FAILED


def test_question_bank_requires_each_level_with_answer_and_explanation():
    artifact = QuestionBankSpecialist().parse(BASIC_ONLY_OUTPUT, "a2").artifact
    assert artifact.status == ArtifactStatus.FAILED
    assert artifact.error_code == "QUESTION_BANK_INCOMPLETE"


def test_extended_reading_rejects_unknown_source():
    artifact = ExtendedReadingSpecialist().parse(
        "## 延伸阅读\n内容[资料99]", "a3", source_allowlist=["资料1"]
    ).artifact
    assert artifact.status == ArtifactStatus.FAILED


def test_cs_practice_requires_nonempty_starter_code():
    artifact = AdaptivePracticeSpecialist().parse(CODE_LAB_WITHOUT_STARTER, "a4", SubjectCategory.CS).artifact
    assert artifact.status == ArtifactStatus.FAILED
```

- [ ] **Step 2: Verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/test_resource_bundle_specialists.py backend/tests/test_resource_bundle_safety.py -q
```

Expected: the four permissive cases pass unexpectedly.

- [ ] **Step 3: Implement shared parser context and exact gates**

Change the specialist interface to:

```python
def parse(
    self,
    raw_output: str,
    artifact_id: str,
    *,
    source_allowlist: tuple[str, ...] = (),
    subject_category: SubjectCategory = SubjectCategory.OTHER,
) -> SpecialistResult:
    ...
```

Every failed artifact must use `body=""`, stable `quality_issues`, and a bounded public `error_code`. Course requires 5/5 sections; question bank requires at least one complete question per level; extended reading validates every citation or the exact no-source declaration; CS practice requires all six sections and nonempty starter code; non-CS practice requires all five sections. Mind map requires nonempty Mermaid and outline blocks.

- [ ] **Step 4: Verify GREEN**

Run the Step 2 command. Expected: all pass.

- [ ] **Step 5: Commit**

```powershell
git add backend/services/resource_bundle/specialists backend/services/resource_bundle/safety.py backend/tests/test_resource_bundle_specialists.py backend/tests/test_resource_bundle_safety.py
git commit -m "fix: enforce five resource quality contracts"
```

### Task 3: Make bundle persistence session-scoped and consistent

**Files:**
- Modify: `backend/database.py`
- Modify: `backend/services/resource_db.py`
- Modify: `backend/services/db.py`
- Test: `backend/tests/test_resource_bundle_db.py`

- [ ] **Step 1: Write failing persistence tests**

```python
def test_save_bundle_writes_session_and_all_artifacts(db):
    bundle = make_bundle_with_two_artifacts()
    save_bundle(db, "session-1", bundle)
    db.commit()
    loaded = get_bundle_for_session(db, "session-1", bundle.bundle_id)
    assert loaded is not None
    assert loaded.session_id == "session-1"
    assert len(loaded.bundle.artifacts) == 2


def test_bundle_is_not_readable_from_other_session(db):
    save_bundle(db, "owner", make_bundle())
    db.commit()
    assert get_bundle_for_session(db, "other", BUNDLE_ID) is None


def test_delete_session_removes_owned_bundles(db):
    save_bundle(db, "session-1", make_bundle())
    repo.delete_session(db, "session-1")
    assert list_bundles(db, "session-1") == []
```

- [ ] **Step 2: Verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/test_resource_bundle_db.py -q
```

Expected: session ID is empty, artifact child rows are absent, and cross-session lookup is possible.

- [ ] **Step 3: Implement one canonical repository transaction**

```python
def save_bundle(db: Session, session_id: str, bundle: ResourceBundle) -> None:
    _upsert_bundle_metadata(db, session_id, bundle)
    for artifact in bundle.artifacts:
        save_artifact(db, bundle.bundle_id, artifact)
    db.execute(
        text("DELETE FROM resource_artifacts WHERE bundle_id=:bid AND artifact_id NOT IN :ids"),
        {"bid": bundle.bundle_id, "ids": tuple(a.artifact_id for a in bundle.artifacts)},
    )
```

Use a safe SQLAlchemy expanding bind for `ids`; do not interpolate IDs. Add `get_bundle_for_session`, `list_bundles`, `replace_artifact`, and deletion cleanup. Treat child artifact rows as canonical; `artifacts_json` remains an export snapshot written in the same transaction.

- [ ] **Step 4: Verify GREEN**

Run the Step 2 command. Expected: all pass.

- [ ] **Step 5: Commit**

```powershell
git add backend/database.py backend/services/resource_db.py backend/services/db.py backend/tests/test_resource_bundle_db.py
git commit -m "fix: persist resource bundles by session"
```

### Task 4: Add pipeline events and cancellable model calls

**Files:**
- Modify: `backend/services/resource_bundle/cancel.py`
- Modify: `backend/services/resource_bundle/pipeline.py`
- Modify: `backend/protocols/v2/sse_events.py`
- Test: `backend/tests/test_resource_bundle_pipeline.py`
- Test: `backend/tests/test_resource_bundle_sse.py`

- [ ] **Step 1: Write failing event and cancellation tests**

```python
@pytest.mark.asyncio
async def test_pipeline_emits_plan_progress_artifacts_and_final_bundle():
    events = []
    result = await pipeline.run(..., on_event=events.append)
    assert [event["event"] for event in events] == [
        "resource_plan",
        "resource_progress", "resource_artifact",
        "resource_progress", "resource_artifact",
        "resource_bundle",
    ]
    assert result.bundle.status == BundleStatus.COMPLETED


@pytest.mark.asyncio
async def test_cancel_interrupts_running_completion():
    gateway = BlockingGateway()
    task = asyncio.create_task(pipeline.run(...))
    await gateway.started.wait()
    cancellation.cancel()
    result = await asyncio.wait_for(task, timeout=1)
    assert gateway.cancelled is True
    assert result.bundle.status == BundleStatus.CANCELLED
```

- [ ] **Step 2: Verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/test_resource_bundle_pipeline.py backend/tests/test_resource_bundle_sse.py -q
```

Expected: no callback API exists and active completion remains running.

- [ ] **Step 3: Implement cancellable completion and event sink**

```python
EventSink = Callable[[dict[str, object]], Awaitable[None]]


async def _complete_or_cancel(gateway, messages, temperature, cancellation):
    model_task = asyncio.create_task(gateway.complete(messages, temperature=temperature))
    cancel_task = asyncio.create_task(cancellation.event.wait())
    done, _ = await asyncio.wait({model_task, cancel_task}, return_when=asyncio.FIRST_COMPLETED)
    if cancel_task in done:
        model_task.cancel()
        with suppress(asyncio.CancelledError):
            await model_task
        raise BundleCancelled()
    cancel_task.cancel()
    return await model_task
```

Use `try/finally` for cancellation registry cleanup. Emit actual planner topic, bounded progress, each validated artifact, and the final bundle. Keep the semaphore at two.

- [ ] **Step 4: Verify GREEN**

Run the Step 2 command. Expected: all pass.

- [ ] **Step 5: Commit**

```powershell
git add backend/services/resource_bundle/cancel.py backend/services/resource_bundle/pipeline.py backend/protocols/v2/sse_events.py backend/tests/test_resource_bundle_pipeline.py backend/tests/test_resource_bundle_sse.py
git commit -m "feat: stream cancellable resource bundle progress"
```

### Task 5: Introduce the shared ResourceBundleService

**Files:**
- Create: `backend/services/resource_bundle/service.py`
- Create: `backend/tests/test_resource_bundle_service.py`
- Modify: `backend/services/orchestrator.py`
- Modify: `backend/routers/resource.py`
- Modify: `backend/services/db.py`

- [ ] **Step 1: Write failing service tests**

```python
@pytest.mark.asyncio
async def test_service_passes_learning_knowledge_and_sources_to_pipeline(db):
    service = make_service(captured_pipeline)
    await service.generate(db, "session-1", "一次函数", ResourceSelection.bundle())
    call = captured_pipeline.calls[0]
    assert "薄弱知识点" in call.learning_context
    assert "资料1" in call.knowledge_context
    assert call.source_allowlist == ["资料1"]


@pytest.mark.asyncio
async def test_service_restores_profiled_state_after_success_and_failure(db):
    await service.generate(...)
    assert repo.get_session(db, "session-1").state == SessionState.PROFILED.value
    failing_pipeline.raise_error = True
    with pytest.raises(AppError):
        await service.generate(...)
    assert repo.get_session(db, "session-1").state == SessionState.PROFILED.value


@pytest.mark.asyncio
async def test_v2_request_never_returns_v1_cache(db):
    seed_v1_cache(db, message="same")
    result = await service.generate(db, "session-1", "same", ResourceSelection.bundle())
    assert result.bundle.protocol_version == "learning-resource-bundle/v2"
```

- [ ] **Step 2: Verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/test_resource_bundle_service.py -q
```

Expected: service module does not exist.

- [ ] **Step 3: Implement the service boundary**

```python
class ResourceBundleService:
    async def generate(
        self,
        db: Session,
        session_id: str,
        message: str,
        selection: ResourceSelection,
        *,
        generation_id: str,
        is_disconnected: Callable[[], Awaitable[bool]],
        on_event: EventSink,
    ) -> ResourceBundle:
        session = require_profiled_session(db, session_id)
        repo.begin_generation(db, session)
        try:
            learning_context = learning.learning_context(db, session_id)
            knowledge = retrieve_knowledge_context(db, session_id, build_query(...))
            public_sources = await search_web_optional(message)
            bundle = await self.pipeline.run(...)
            save_bundle(db, session_id, bundle)
            repo.finish_bundle_generation(db, session)
            db.commit()
            return bundle
        except Exception:
            repo.fail_to_stable_state(db, session, "BUNDLE_FAILED")
            raise
```

The service must map model and protocol failures to stable `AppError` codes and never return `str(exc)` to the renderer.

- [ ] **Step 4: Replace duplicated router and orchestrator logic**

Both `/api/resource-bundle` and chat paths call the same service. `orchestrator.py` only translates service callbacks into SSE dictionaries.

- [ ] **Step 5: Verify GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/test_resource_bundle_service.py backend/tests/test_orchestrator.py backend/tests/test_resource_bundle_api.py -q
```

Expected: all pass.

- [ ] **Step 6: Commit**

```powershell
git add backend/services/resource_bundle/service.py backend/tests/test_resource_bundle_service.py backend/services/orchestrator.py backend/routers/resource.py backend/services/db.py backend/tests/test_orchestrator.py backend/tests/test_resource_bundle_api.py
git commit -m "feat: unify resource bundle session orchestration"
```

### Task 6: Add typed HTTP, SSE, history, and retry contracts

**Files:**
- Modify: `backend/models/schemas.py`
- Modify: `backend/routers/chat.py`
- Modify: `backend/routers/resource.py`
- Modify: `backend/routers/sessions.py`
- Modify: `backend/services/resource_bundle/service.py`
- Create: `backend/tests/test_resource_bundle_orchestrator_integration.py`

- [ ] **Step 1: Write failing contract tests**

```python
def test_nonstream_chat_returns_bundle(client, profiled_session, fake_bundle_service):
    response = client.post("/api/chat", json={
        "session_id": profiled_session,
        "message": "生成资源",
        "resource_mode": "bundle",
    })
    assert response.status_code == 200
    assert response.json()["bundle"]["status"] == "COMPLETED"


def test_stream_emits_each_artifact_and_restores_state(client, profiled_session):
    events = read_sse(...)
    assert sum(event["event"] == "resource_artifact" for event in events) == 5
    assert events[-1]["state"] == "PROFILED"


def test_retry_replaces_only_failed_artifact(client, partial_bundle):
    response = client.post(
        f"/api/resource-bundles/{partial_bundle.bundle_id}/artifacts/mind_map/retry",
        json={"session_id": partial_bundle.session_id},
    )
    assert response.status_code == 200
    assert response.json()["bundle"]["artifacts"][1]["status"] == "SUCCEEDED"
```

- [ ] **Step 2: Verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/test_resource_bundle_api.py backend/tests/test_resource_bundle_orchestrator_integration.py -q
```

Expected: response lacks bundle, no artifact events exist, retry route is 404.

- [ ] **Step 3: Implement strict schemas and routes**

Use `ConfigDict(extra="forbid")` for request models. Add `bundle: ResourceBundleResponse | None` to `ChatResponse`, session-scoped `ResourceBundleHistoryItem`, and a fixed `RetryArtifactRequest` containing only `session_id`.

- [ ] **Step 4: Verify GREEN**

Run the Step 2 command. Expected: all pass.

- [ ] **Step 5: Commit**

```powershell
git add backend/models/schemas.py backend/routers/chat.py backend/routers/resource.py backend/routers/sessions.py backend/services/resource_bundle/service.py backend/tests/test_resource_bundle_api.py backend/tests/test_resource_bundle_orchestrator_integration.py
git commit -m "feat: expose bundle history and artifact retry"
```

### Task 7: Add strict frontend and Electron contracts

**Files:**
- Modify: `a3-front/a3-front/src/api/types.ts`
- Modify: `a3-front/a3-front/src/api/backend.ts`
- Modify: `a3-front/a3-front/src/api/backend.test.ts`
- Modify: `a3-front/a3-front/electron/ipc-contract.mjs`
- Modify: `a3-front/a3-front/electron/ipc-contract.test.mjs`

- [ ] **Step 1: Write failing API and IPC tests**

```typescript
it('sends bundle and single selections through chat and stream', async () => {
  await backendApi.streamChat('s1', '生成', onEvent, signal, { mode: 'single', resourceType: 'mind_map' })
  expect(transport.last.body).toEqual({
    session_id: 's1', message: '生成', resource_mode: 'single', resource_type: 'mind_map',
  })
})
```

```javascript
test('chat body permits only fixed resource selection fields', () => {
  expectAccepted({ method: 'POST', path: '/api/chat/stream', body: {
    session_id: 's1', message: 'x', resource_mode: 'bundle',
  }}, { stream: true })
  expectRejected({ method: 'POST', path: '/api/chat', body: {
    message: 'x', resource_mode: 'single', resource_type: 'unknown', model_profile: 'secret',
  }})
})
```

- [ ] **Step 2: Verify RED**

Run:

```powershell
npx vitest run src/api/backend.test.ts
node --test electron/ipc-contract.test.mjs
```

Expected: backend methods lack options and IPC accepts unknown nested fields.

- [ ] **Step 3: Implement discriminated types and fixed IPC body validation**

```typescript
export type ResourceSelection =
  | { mode: 'bundle' }
  | { mode: 'single'; resourceType: ArtifactType }

export type StreamEvent =
  | PhaseEvent | DeltaEvent | ErrorEvent
  | ResourcePlanEvent | ResourceProgressEvent | ResourceArtifactEvent | ResourceBundleEvent
```

`backendApi.chat` and `streamChat` append only the two allowed resource fields. Electron validates `session_id`, `message`, mode/type dependency, and rejects all extra chat body fields.

- [ ] **Step 4: Verify GREEN**

Run the Step 2 commands. Expected: all pass.

- [ ] **Step 5: Commit**

```powershell
git add a3-front/a3-front/src/api/types.ts a3-front/a3-front/src/api/backend.ts a3-front/a3-front/src/api/backend.test.ts a3-front/a3-front/electron/ipc-contract.mjs a3-front/a3-front/electron/ipc-contract.test.mjs
git commit -m "feat: add typed desktop resource bundle contracts"
```

### Task 8: Replace unsafe rendering and harden Mermaid

**Files:**
- Create: `a3-front/a3-front/src/components/learning/SafeMarkdown.vue`
- Create: `a3-front/a3-front/src/tests/components/SafeMarkdown.test.ts`
- Modify: `a3-front/a3-front/src/components/learning/ResourceCard.vue`
- Modify: `a3-front/a3-front/src/components/learning/SafeMermaid.vue`
- Modify: `a3-front/a3-front/src/tests/components/ResourceBundle.test.ts`
- Modify: `a3-front/a3-front/src/tests/components/SafeMermaid.test.ts`

- [ ] **Step 1: Write failing renderer tests**

```typescript
it('never inserts model HTML', () => {
  const wrapper = mount(SafeMarkdown, { props: { content: '<img src=x onerror=alert(1)>\n## 标题' } })
  expect(wrapper.find('img').exists()).toBe(false)
  expect(wrapper.text()).toContain('<img src=x onerror=alert(1)>')
})


it('uses SafeMermaid for mind maps and hides copy for failed bodies', async () => {
  const wrapper = mount(ResourceCard, { props: { artifact: failedUnsafeMindMap } })
  await wrapper.find('.card-header').trigger('click')
  expect(wrapper.findComponent(SafeMermaid).exists()).toBe(false)
  expect(wrapper.find('.copy-btn').exists()).toBe(false)
})


it('falls back after mermaid.render rejects', async () => {
  mermaidRender.mockRejectedValue(new Error('parse'))
  const wrapper = mount(SafeMermaid, { props: { content: VALID_GRAPH, outline: '- A' } })
  await flushPromises()
  expect(wrapper.find('.outline-fallback').exists()).toBe(true)
})
```

- [ ] **Step 2: Verify RED**

Run:

```powershell
npx vitest run src/tests/components/SafeMarkdown.test.ts src/tests/components/ResourceBundle.test.ts src/tests/components/SafeMermaid.test.ts
```

Expected: model HTML becomes an actual element, mind map bypasses SafeMermaid, and render rejection leaves an empty container.

- [ ] **Step 3: Implement token rendering without v-html**

`SafeMarkdown` splits bounded text into heading, paragraph, list and fenced-code tokens and renders them with Vue templates using interpolation. It does not accept raw HTML or arbitrary links.

`SafeMermaid` adds `renderFailed`, watches content changes, limits source to 20,000 characters and 250 lines, rejects init/click/HTML directives, and uses a monotonic component ID. Any failure sets `renderFailed=true` and displays the outline.

- [ ] **Step 4: Verify GREEN**

Run the Step 2 command. Expected: all pass.

- [ ] **Step 5: Commit**

```powershell
git add a3-front/a3-front/src/components/learning/SafeMarkdown.vue a3-front/a3-front/src/tests/components/SafeMarkdown.test.ts a3-front/a3-front/src/components/learning/ResourceCard.vue a3-front/a3-front/src/components/learning/SafeMermaid.vue a3-front/a3-front/src/tests/components/ResourceBundle.test.ts a3-front/a3-front/src/tests/components/SafeMermaid.test.ts
git commit -m "fix: render generated resources without executable HTML"
```

### Task 9: Connect SmartTutor, progress, history, and retry

**Files:**
- Modify: `a3-front/a3-front/src/components/learning/ResourceMenu.vue`
- Modify: `a3-front/a3-front/src/components/learning/ResourceBundle.vue`
- Modify: `a3-front/a3-front/src/views/SmartTutor.vue`
- Modify: `a3-front/a3-front/src/views/SmartTutor.test.ts`
- Modify: `a3-front/a3-front/src/stores/backend.ts`
- Modify: `a3-front/a3-front/src/stores/backend.test.ts`

- [ ] **Step 1: Write failing SmartTutor integration tests**

```typescript
it('sends the selected bundle mode from the composer', async () => {
  const wrapper = mountTutorWithProfiledSession()
  await wrapper.find('[data-testid="resource-mode"]').setValue('single:mind_map')
  await wrapper.find('textarea').setValue('生成导图')
  await wrapper.find('[data-testid="send"]').trigger('click')
  expect(streamChat).toHaveBeenCalledWith(
    expect.any(String), '生成导图', expect.any(Function), expect.any(AbortSignal),
    { mode: 'single', resourceType: 'mind_map' },
  )
})


it('renders artifact progress and the final bundle', async () => {
  streamChat.mockImplementation(async (_s, _m, emit) => {
    emit(resourceProgressEvent)
    emit(resourceArtifactEvent)
    emit(resourceBundleEvent)
  })
  const wrapper = mountTutorWithProfiledSession()
  await sendBundle(wrapper)
  expect(wrapper.text()).toContain('1 / 5')
  expect(wrapper.findComponent(ResourceBundle).exists()).toBe(true)
})


it('restores bundles from session history and retries one artifact', async () => {
  const wrapper = mountTutorWithHistory(partialBundle)
  await wrapper.find('.retry-btn').trigger('click')
  expect(retryResourceArtifact).toHaveBeenCalledWith(partialBundle.bundle_id, 'mind_map', SESSION_ID)
})
```

- [ ] **Step 2: Verify RED**

Run:

```powershell
npx vitest run src/views/SmartTutor.test.ts src/stores/backend.test.ts
```

Expected: selector absent, events ignored, bundles absent from history, retry not called.

- [ ] **Step 3: Implement the desktop UI closure**

Keep `resourceSelection` defaulted to bundle. Show the selector only for profiled/generating-capable sessions. Store `activeBundle`, `resourceProgress`, and retrying artifact IDs. On `resource_bundle`, replace the provisional bundle; after `done`, refresh history. Historical v1 messages remain `<pre>` text while v2 bundles use `ResourceBundle`.

- [ ] **Step 4: Verify GREEN**

Run the Step 2 command. Expected: all pass.

- [ ] **Step 5: Commit**

```powershell
git add a3-front/a3-front/src/components/learning/ResourceMenu.vue a3-front/a3-front/src/components/learning/ResourceBundle.vue a3-front/a3-front/src/views/SmartTutor.vue a3-front/a3-front/src/views/SmartTutor.test.ts a3-front/a3-front/src/stores/backend.ts a3-front/a3-front/src/stores/backend.test.ts
git commit -m "feat: connect resource bundles to Smart Tutor"
```

### Task 10: Full regression and packaged desktop acceptance

**Files:**
- Modify: `backend/tests/test_resource_bundle_api.py`
- Modify: `backend/tests/test_resource_bundle_db.py`
- Modify: `backend/tests/test_resource_bundle_pipeline.py`
- Modify: `a3-front/a3-front/src/views/SmartTutor.test.ts`
- Modify: `codex/AI模型任务队列.md`

- [ ] **Step 1: Replace permissive tests with exact assertions**

Every API test must assert one expected status and structured payload. Add tests for v1 cache isolation, session restoration, cancellation ownership, five artifact events, source snapshots, narrow-screen controls, history restore, XSS nonexecution and retry replacement.

- [ ] **Step 2: Run backend bundle and integration suites**

```powershell
$env:A3_DATA_DIR='E:\软件杯\.tmp\s022-remediation-tests'
.\.venv\Scripts\python.exe -m pytest backend/tests/test_resource_bundle_*.py backend/tests/test_orchestrator.py backend/tests/test_streaming.py -q
```

Expected: all pass, no resource bundle failures.

- [ ] **Step 3: Run the complete isolated backend suite**

```powershell
$env:A3_DATA_DIR='E:\软件杯\.tmp\s022-remediation-full'
.\.venv\Scripts\python.exe -m pytest backend/tests -q
```

Expected: all tests pass; skipped optional integration tests are reported separately.

- [ ] **Step 4: Run Electron, Vitest, and desktop build**

```powershell
cd a3-front\a3-front
npm test
npm run build:desktop
```

Expected: Node and Vitest report zero failures; build exits 0 and includes the resource UI strings in `dist`.

- [ ] **Step 5: Verify unpacked application lifecycle**

Run the existing packaged test-mode launch with an isolated userData directory. Confirm backend ready, one bundle generation with five cards, a single-mode request, cancel, retry, history restore, clean exit and zero residual processes.

- [ ] **Step 6: Update queue and commit**

Record exact commands, pass counts, build result, packaged lifecycle and remaining non-blocking limitations.

```powershell
git add backend/tests a3-front/a3-front/src a3-front/a3-front/electron codex/AI模型任务队列.md
git commit -m "test: verify five-resource desktop closure"
```

---

## Self-Review

### Spec coverage

- Desktop selector and five cards: Tasks 7–9.
- Profile, learning, knowledge and public sources: Task 5.
- Maximum two concurrent specialists: Task 4 regression.
- Partial success and independent retry: Tasks 3, 4 and 6.
- Cancellation and disconnect: Tasks 4–6.
- Session-scoped persistence and history: Tasks 3, 6 and 9.
- Exact five-type quality gates and citations: Task 2.
- v1 compatibility and cache isolation: Tasks 5, 6 and 10.
- Safe Markdown and Mermaid: Task 8.
- Full and packaged verification: Task 10.

### Type consistency

`ArtifactType`, `ResourceSelection`, `ResourceBundleResponse`, `ResourceArtifact`, and resource SSE event names are defined once and reused through backend schema, TypeScript types, IPC validation and UI components.

### Scope boundary

This plan repairs S-022 and adds only the minimum renderer safety required to expose model output. Semantic content moderation, PII/secret scanning, Safety Reviewer Agent and policy audit belong to the separate S-026 plan executed after this plan passes.
