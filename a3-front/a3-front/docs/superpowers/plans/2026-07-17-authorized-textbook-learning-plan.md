# Authorized Textbook Learning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在桌面端提供合法的初高中数学教材目录，并让已导入教材可靠驱动知识点总结、例题生成和分步解题。

**Architecture:** FastAPI 提供只读、版本化、白名单化教材目录；人教版记录只包含官方在线阅读元数据，Electron 仅打开后端返回且主进程再次校验的白名单 URL。可检索正文仍来自本地导入或明确开放许可下载；知识库卡片通过路由参数把集合和预填问题交给 SmartTutor，现有检索、内容安全和可信引用链继续负责模型上下文。

**Tech Stack:** FastAPI、Pydantic、Vue 3、Vue Router、Electron IPC、Vitest、pytest、现有 Resource Bundle v2 与 content-safety/v1

---

## File Structure

- Create: `backend/knowledge/textbook_catalog.py` — 受控教材条目、筛选和来源白名单。
- Modify: `backend/knowledge/schemas.py` — 教材目录响应类型。
- Modify: `backend/routers/knowledge.py` — 只读教材目录端点。
- Create: `backend/tests/knowledge/test_textbook_catalog.py` — 版权模式、筛选和 URL 白名单测试。
- Modify: `backend/tests/knowledge/test_knowledge_api.py` — API 契约测试。
- Modify: `a3-front/a3-front/src/api/types.ts` — 教材目录类型。
- Modify: `a3-front/a3-front/src/api/backend.ts` — 目录请求。
- Modify: `a3-front/a3-front/src/api/backend.test.ts` — 传输契约。
- Create: `a3-front/a3-front/src/components/knowledge/TextbookCatalog.vue` — 初高中数学目录与筛选。
- Create: `a3-front/a3-front/src/components/knowledge/TextbookCatalog.test.ts` — 目录行为测试。
- Modify: `a3-front/a3-front/src/views/KnowledgeLibrary.vue` — 目录入口与教材学习动作。
- Modify: `a3-front/a3-front/src/views/KnowledgeLibrary.test.ts` — 路由联动测试。
- Modify: `a3-front/a3-front/electron/preload.cjs` — 暴露受控教材外链 IPC。
- Modify: `a3-front/a3-front/electron/ipc-contract.mjs` — 教材来源 ID/URL 契约。
- Modify: `a3-front/a3-front/electron/ipc-contract.test.mjs` — 任意 URL 拒绝测试。
- Modify: `a3-front/a3-front/electron/main.mjs` — 白名单外链打开。
- Modify: `a3-front/a3-front/electron/runtime.test.mjs` — 主进程接线测试。
- Modify: `a3-front/a3-front/src/views/SmartTutor.vue` — 接收知识集合与预填请求。
- Modify: `a3-front/a3-front/src/views/SmartTutor.test.ts` — 预填、绑定与发送测试。
- Modify: `backend/services/resource_bundle/specialists/course_explanation.py` — 教材总结结构。
- Modify: `backend/services/resource_bundle/specialists/question_bank.py` — 分步解题结构。
- Modify: `backend/services/resource_bundle/specialists/adaptive_practice.py` — 练习解析与检查。
- Modify: `backend/tests/test_resource_bundle_specialists.py` — 提示词和输出质量门测试。
- Modify: `backend/tests/test_resource_bundle_service.py` — 教材引用端到端上下文测试。
- Modify: `codex/AI模型任务队列.md` — 验收证据。

### Task 1: Add a versioned, readonly official textbook catalog

**Files:**
- Create: `backend/knowledge/textbook_catalog.py`
- Modify: `backend/knowledge/schemas.py`
- Modify: `backend/routers/knowledge.py`
- Create: `backend/tests/knowledge/test_textbook_catalog.py`
- Modify: `backend/tests/knowledge/test_knowledge_api.py`

- [ ] **Step 1: Write failing catalog model tests**

```python
def test_pep_entries_are_official_reader_only():
    entries = list_textbooks(stage="高中", subject="数学", publisher="人民教育出版社")
    assert entries
    assert all(item.access_mode == "OFFICIAL_READER" for item in entries)
    assert all(item.official_url.startswith("https://book.pep.com.cn/") for item in entries)
    assert all(item.download_url is None for item in entries)

def test_catalog_rejects_unapproved_hosts():
    with pytest.raises(ValueError, match="host"):
        TextbookCatalogItem(source_id="bad", official_url="https://attacker.example/book", access_mode="OFFICIAL_READER", **required_fields())
```

- [ ] **Step 2: Run tests and verify RED**

```powershell
python -m pytest backend/tests/knowledge/test_textbook_catalog.py backend/tests/knowledge/test_knowledge_api.py -q
```

Expected: FAIL because catalog models and endpoint do not exist.

- [ ] **Step 3: Implement strict catalog data and filters**

Define immutable entries and allowed hosts:

```python
ALLOWED_TEXTBOOK_HOSTS = {"jc.pep.com.cn", "book.pep.com.cn"}

class TextbookCatalogItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    source_id: str
    publisher: str
    title: str
    stage: Literal["初中", "高中"]
    grade: str
    semester: str
    subject: Literal["数学"]
    edition: str
    official_url: HttpUrl
    access_mode: Literal["OFFICIAL_READER", "LICENSED_DOWNLOAD", "EXTERNAL_CATALOG"]
    license_note: str
    verified_at: date
    download_url: HttpUrl | None = None
```

Validate both URLs against the host set and require `download_url is None` for every PEP `OFFICIAL_READER` item. Populate current official junior/high mathematics entries from the verified PEP catalog; include no copied page images or book text.

- [ ] **Step 4: Add the API endpoint**

```python
@router.get("/textbooks", response_model=TextbookCatalogResponse)
def textbook_catalog(
    stage: Literal["初中", "高中"] | None = None,
    subject: Literal["数学"] = "数学",
    publisher: str | None = None,
):
    return TextbookCatalogResponse(version="2026-07-17", items=list_textbooks(stage, subject, publisher))
```

- [ ] **Step 5: Run tests and verify GREEN**

Run the Step 2 command. Expected: catalog and API tests pass.

- [ ] **Step 6: Commit**

```powershell
git add -- backend/knowledge/textbook_catalog.py backend/knowledge/schemas.py backend/routers/knowledge.py backend/tests/knowledge/test_textbook_catalog.py backend/tests/knowledge/test_knowledge_api.py
git commit -m "feat: add authorized textbook catalog"
```

### Task 2: Expose catalog types and a safe desktop open action

**Files:**
- Modify: `a3-front/a3-front/src/api/types.ts`
- Modify: `a3-front/a3-front/src/api/backend.ts`
- Modify: `a3-front/a3-front/src/api/backend.test.ts`
- Modify: `a3-front/a3-front/electron/ipc-contract.mjs`
- Modify: `a3-front/a3-front/electron/ipc-contract.test.mjs`
- Modify: `a3-front/a3-front/electron/preload.cjs`
- Modify: `a3-front/a3-front/electron/main.mjs`
- Modify: `a3-front/a3-front/electron/runtime.test.mjs`

- [ ] **Step 1: Write failing frontend and IPC tests**

Require `backendApi.textbookCatalog({ stage: '高中', subject: '数学' })` to call `/api/knowledge/textbooks`, and require the desktop bridge to accept only a server-issued catalog item:

```javascript
assert.deepEqual(validateTextbookOpen({ sourceId: 'pep-high-a1', url: 'https://book.pep.com.cn/1421001121191/' }), {
  ok: true,
  value: { sourceId: 'pep-high-a1', url: 'https://book.pep.com.cn/1421001121191/' },
})
assert.equal(validateTextbookOpen({ sourceId: 'x', url: 'https://attacker.example/' }).ok, false)
```

- [ ] **Step 2: Run tests and verify RED**

```powershell
node --test a3-front/a3-front/electron/ipc-contract.test.mjs a3-front/a3-front/electron/runtime.test.mjs
Set-Location a3-front/a3-front
npx vitest run src/api/backend.test.ts
```

Expected: FAIL because the catalog API and IPC action do not exist.

- [ ] **Step 3: Add strict types and API call**

```typescript
export interface TextbookCatalogItem {
  source_id: string
  publisher: string
  title: string
  stage: '初中' | '高中'
  grade: string
  semester: string
  subject: '数学'
  edition: string
  official_url: string
  access_mode: 'OFFICIAL_READER' | 'LICENSED_DOWNLOAD' | 'EXTERNAL_CATALOG'
  license_note: string
  verified_at: string
  download_url: string | null
}
```

Add `textbookCatalog()` to `backendApi` and `textbookOpenOfficial(sourceId, url)` to the desktop bridge.

- [ ] **Step 4: Validate again in the main process**

`validateTextbookOpen` must require HTTPS, reject credentials/fragments, accept only `jc.pep.com.cn` and `book.pep.com.cn`, and require a bounded `sourceId`. The main process calls `shell.openExternal(validated.value.url)` only after validation.

- [ ] **Step 5: Run tests and verify GREEN**

Run the Step 2 commands. Expected: all targeted tests pass, including arbitrary-host rejection.

- [ ] **Step 6: Commit**

```powershell
git add -- a3-front/a3-front/src/api/types.ts a3-front/a3-front/src/api/backend.ts a3-front/a3-front/src/api/backend.test.ts a3-front/a3-front/electron/ipc-contract.mjs a3-front/a3-front/electron/ipc-contract.test.mjs a3-front/a3-front/electron/preload.cjs a3-front/a3-front/electron/main.mjs a3-front/a3-front/electron/runtime.test.mjs
git commit -m "feat: open official textbook sources safely"
```

### Task 3: Build the textbook catalog UI

**Files:**
- Create: `a3-front/a3-front/src/components/knowledge/TextbookCatalog.vue`
- Create: `a3-front/a3-front/src/components/knowledge/TextbookCatalog.test.ts`
- Modify: `a3-front/a3-front/src/views/KnowledgeLibrary.vue`
- Modify: `a3-front/a3-front/src/views/KnowledgeLibrary.test.ts`

- [ ] **Step 1: Write failing UI tests**

```typescript
it('filters junior and high school math and labels access mode', async () => {
  const wrapper = mount(TextbookCatalog, { props: { items: catalogItems } })
  await wrapper.get('[aria-label="选择高中教材"]').trigger('click')
  expect(wrapper.text()).toContain('普通高中教科书数学必修第一册（A版）')
  expect(wrapper.text()).toContain('人教社官方在线阅读')
  expect(wrapper.text()).not.toContain('下载到知识库')
})
```

- [ ] **Step 2: Run tests and verify RED**

```powershell
Set-Location a3-front/a3-front
npx vitest run src/components/knowledge/TextbookCatalog.test.ts src/views/KnowledgeLibrary.test.ts
```

Expected: FAIL because the component does not exist.

- [ ] **Step 3: Implement catalog tabs and cards**

Create a compact component with `初中/高中` tabs, publisher and edition labels, and one action per access mode. For PEP items render:

```vue
<button :aria-label="`在线阅读 ${item.title}`" @click="$emit('open', item)">人教社官方在线阅读</button>
<p>{{ item.license_note }}</p>
```

Do not render download controls when `access_mode === 'OFFICIAL_READER'`.

- [ ] **Step 4: Connect it to KnowledgeLibrary**

Load catalog data on mount, add a “教材目录” section, and route `open` through `backendApi.openOfficialTextbook`. A failed official link shows a user-facing error and does not alter the knowledge library.

- [ ] **Step 5: Run tests and verify GREEN**

Run the Step 2 command. Expected: component and page tests pass.

- [ ] **Step 6: Commit**

```powershell
git add -- a3-front/a3-front/src/components/knowledge/TextbookCatalog.vue a3-front/a3-front/src/components/knowledge/TextbookCatalog.test.ts a3-front/a3-front/src/views/KnowledgeLibrary.vue a3-front/a3-front/src/views/KnowledgeLibrary.test.ts
git commit -m "feat: show official math textbook catalog"
```

### Task 4: Add knowledge-summary and worked-example actions

**Files:**
- Modify: `a3-front/a3-front/src/components/knowledge/DocumentInspector.test.ts`
- Modify: `a3-front/a3-front/src/components/knowledge/DocumentInspector.vue`
- Modify: `a3-front/a3-front/src/views/KnowledgeLibrary.test.ts`
- Modify: `a3-front/a3-front/src/views/KnowledgeLibrary.vue`
- Modify: `a3-front/a3-front/src/views/SmartTutor.test.ts`
- Modify: `a3-front/a3-front/src/views/SmartTutor.vue`

- [ ] **Step 1: Write failing action and routing tests**

Require completed documents to emit `summarize` and `worked-example`. Require KnowledgeLibrary to navigate with a bounded prompt and collection ID:

```typescript
expect(routerPush).toHaveBeenCalledWith({
  name: 'smart-tutor',
  query: { knowledge_collection: '7', prompt: expect.stringContaining('总结这份教材') },
})
```

Require SmartTutor to load the collection binding before sending the prefilled prompt.

- [ ] **Step 2: Run tests and verify RED**

```powershell
Set-Location a3-front/a3-front
npx vitest run src/components/knowledge/DocumentInspector.test.ts src/views/KnowledgeLibrary.test.ts src/views/SmartTutor.test.ts
```

Expected: FAIL because the actions and route hydration do not exist.

- [ ] **Step 3: Add document actions**

Add buttons:

```vue
<button @click="$emit('summarize', document.id)">总结知识点</button>
<button @click="$emit('worked-example', document.id)">生成例题与步骤</button>
```

KnowledgeLibrary builds prompts containing the selected document display name but no filesystem path or hash.

- [ ] **Step 4: Hydrate SmartTutor safely**

Read only string query values, cap prompt length at 1000 characters, validate collection ID as a positive integer, call `saveSessionKnowledgeCollections` with that collection before generation, then place the prompt in the existing composer without auto-sending. Remove or replace the query after hydration so refresh does not repeatedly rebind.

- [ ] **Step 5: Run tests and verify GREEN**

Run the Step 2 command. Expected: all targeted tests pass.

- [ ] **Step 6: Commit**

```powershell
git add -- a3-front/a3-front/src/components/knowledge/DocumentInspector.vue a3-front/a3-front/src/components/knowledge/DocumentInspector.test.ts a3-front/a3-front/src/views/KnowledgeLibrary.vue a3-front/a3-front/src/views/KnowledgeLibrary.test.ts a3-front/a3-front/src/views/SmartTutor.vue a3-front/a3-front/src/views/SmartTutor.test.ts
git commit -m "feat: launch textbook learning actions"
```

### Task 5: Require textbook-grounded summaries and step-by-step solutions

**Files:**
- Modify: `backend/tests/test_resource_bundle_specialists.py`
- Modify: `backend/tests/test_resource_bundle_service.py`
- Modify: `backend/services/resource_bundle/specialists/course_explanation.py`
- Modify: `backend/services/resource_bundle/specialists/question_bank.py`
- Modify: `backend/services/resource_bundle/specialists/adaptive_practice.py`

- [ ] **Step 1: Write failing prompt-contract tests**

Assert the course prompt requires concepts, formulas/conditions, dependency relationships, common mistakes and citations. Assert question/practice prompts require:

```python
required_sections = ["已知条件", "目标", "所用知识点", "分步推导", "最终答案", "结果检查"]
for section in required_sections:
    assert section in system_prompt
```

Add a service test with a bound math textbook chunk and assert the pipeline receives `[资料1]`, the trusted source list contains only `资料1`, and unknown `[资料2]` remains blocked by the existing citation gate.

- [ ] **Step 2: Run tests and verify RED**

```powershell
python -m pytest backend/tests/test_resource_bundle_specialists.py backend/tests/test_resource_bundle_service.py -q
```

Expected: at least one new structure assertion fails because existing prompts do not require every section.

- [ ] **Step 3: Strengthen only the three relevant specialist prompts**

Add fixed system instructions, not untrusted user data:

```text
教材总结必须包含：核心概念与定义、公式及适用条件、知识依赖、常见题型、易错点。
数学解题必须按：已知条件与目标、所用知识点及条件、分步推导、最终答案、结果检查 输出。
只有服务器提供的 [资料N] 可以作为教材引用；证据不足时明确说明，不得伪造页码或引用。
```

Retain the current untrusted-data boundary, content-safety review and v2 protocol output format.

- [ ] **Step 4: Run tests and verify GREEN**

Run the Step 2 command. Expected: specialist and service tests pass.

- [ ] **Step 5: Commit**

```powershell
git add -- backend/services/resource_bundle/specialists/course_explanation.py backend/services/resource_bundle/specialists/question_bank.py backend/services/resource_bundle/specialists/adaptive_practice.py backend/tests/test_resource_bundle_specialists.py backend/tests/test_resource_bundle_service.py
git commit -m "feat: require grounded worked solutions"
```

### Task 6: Full acceptance and packaging

**Files:**
- Modify: `codex/AI模型任务队列.md`
- Generated/ignored: `a3-front/a3-front/desktop-backend/`
- Generated/ignored: `a3-front/a3-front/release/`

- [ ] **Step 1: Run catalog, knowledge and safety regressions**

```powershell
python -m pytest backend/tests/knowledge backend/tests/test_resource_bundle_specialists.py backend/tests/test_resource_bundle_service.py backend/tests/test_content_safety_citations.py -q
node --test a3-front/a3-front/electron/ipc-contract.test.mjs a3-front/a3-front/electron/runtime.test.mjs
Set-Location a3-front/a3-front
npm test
npm run type-check
npm run build:desktop
```

Expected: all commands exit 0.

- [ ] **Step 2: Verify official links without downloading copyrighted content**

From the packaged desktop app, open one junior and one high school PEP mathematics entry. Confirm the system browser receives a `book.pep.com.cn` URL. Confirm no textbook page image, PDF or HTML mirror appears in Git status, `desktop-backend` or application source assets.

- [ ] **Step 3: Verify a grounded learning flow**

Bind a successfully imported math document, trigger “总结知识点” and “生成例题与步骤”, and verify the model request receives retrieved textbook context. Accept only output containing the required structure and server-valid `[资料N]` citations. If the configured model is unavailable, run the deterministic fake gateway test and record the real-model check as an environment limitation instead of claiming it passed.

- [ ] **Step 4: Rebuild packaged backend and unpacked desktop app**

Use the repository packaging script, verify backend file hashes, then run:

```powershell
Set-Location a3-front/a3-front
npm run desktop:pack
```

Expected: unpacked app launches, opens official links, uses the current backend, exits with code 0 and leaves zero residual processes.

- [ ] **Step 5: Update queue and commit acceptance evidence**

Mark S-032 complete only after the automated and packaged checks pass. Record exact test counts, official URLs checked, model validation mode and package hashes, then:

```powershell
git add -- codex/AI模型任务队列.md
git commit -m "test: verify authorized textbook learning"
```

## Self-Review

- Spec coverage: Tasks 1–3 implement official/authorized catalog behavior; Task 4 connects documents to SmartTutor; Task 5 enforces summaries, worked solutions and citations; Task 6 verifies copyright boundaries and packaged behavior.
- Type consistency: `TextbookCatalogItem`, `OFFICIAL_READER`, `LICENSED_DOWNLOAD`, `source_id`, `official_url`, `knowledge_collection` and `prompt` remain consistent.
- Scope: no scraper, DRM bypass, PEP mirroring or arbitrary URL downloader is introduced.

