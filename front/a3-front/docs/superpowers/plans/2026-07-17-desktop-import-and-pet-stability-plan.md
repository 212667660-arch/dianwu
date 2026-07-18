# Desktop Import and Pet Stability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复墨团连续交互导致的视觉尺寸不稳定，并让桌面端安全导入、解析和预览最大 500 MiB 的本地教材文件。

**Architecture:** 保留 Electron 主进程流式对象存储、FastAPI 隔离 worker 和只读预览副本。墨团渲染新增纯函数尺寸/交互控制边界，保证动作计时器、画布 backing store 与窗口设置不随点击累积；文件上限在 Electron 与 Pydantic 同步为 500 MiB，并用用户真实 PDF 做端到端验收。

**Tech Stack:** Electron 32、Node.js test runner、Vue 3、Vitest、FastAPI、Pydantic、PyMuPDF、PyInstaller

---

## File Structure

- Modify: `a3-front/a3-front/electron/pet/pet-renderer.js` — 固定逻辑画布、DPR backing store 与幂等动作计时器。
- Modify: `a3-front/a3-front/electron/pet-renderer.test.mjs` — 连续点击、计时器和画布尺寸回归。
- Modify: `a3-front/a3-front/electron/pet-controller.test.mjs` — 连续拖放不改变窗口宽高或缩放。
- Modify: `a3-front/a3-front/electron/knowledge-import.mjs` — 单文件 500 MiB 限额和一致错误文案。
- Modify: `a3-front/a3-front/electron/knowledge-import.test.mjs` — 500 MiB 边界与真实大文件流式复制测试。
- Modify: `backend/knowledge/schemas.py` — 后端单文件 500 MiB 限额。
- Modify: `backend/tests/knowledge/test_schemas.py` — Pydantic 边界测试。
- Modify: `a3-front/a3-front/src/components/knowledge/DocumentInspector.vue` — 明确预览与系统阅读器入口。
- Modify: `a3-front/a3-front/src/components/knowledge/DocumentInspector.test.ts` — 操作文案和事件测试。
- Modify: `a3-front/a3-front/src/views/KnowledgeLibrary.vue` — 连接预览/打开行为并显示大文件状态。
- Modify: `a3-front/a3-front/src/views/KnowledgeLibrary.test.ts` — 知识库页面交互回归。
- Modify: `codex/AI模型任务队列.md` — 逐任务记录验证证据。

### Task 1: Make pet interaction and canvas sizing idempotent

**Files:**
- Modify: `a3-front/a3-front/electron/pet-renderer.test.mjs`
- Modify: `a3-front/a3-front/electron/pet/pet-renderer.js`

- [ ] **Step 1: Write failing interaction and canvas tests**

Add tests that describe the stable API:

```javascript
import {
  canvasBackingSize,
  createInteractionController,
} from './pet/pet-renderer.js'

test('one interaction timer survives repeated clicks', () => {
  const timers = new Map()
  let nextId = 0
  const states = []
  const controller = createInteractionController({
    onState: state => states.push(state),
    durationFor: () => 400,
    setTimer: callback => { const id = ++nextId; timers.set(id, callback); return id },
    clearTimer: id => timers.delete(id),
  })
  for (let index = 0; index < 100; index += 1) controller.play('waving')
  assert.equal(timers.size, 1)
  assert.equal(states.at(-1), 'waving')
  timers.values().next().value()
  assert.equal(states.at(-1), null)
})

test('canvas backing size depends only on logical size and clamped dpr', () => {
  assert.deepEqual(canvasBackingSize({ width: 192, height: 208 }, 1), { width: 192, height: 208, dpr: 1 })
  assert.deepEqual(canvasBackingSize({ width: 192, height: 208 }, 2.5), { width: 480, height: 520, dpr: 2.5 })
  assert.deepEqual(canvasBackingSize({ width: 192, height: 208 }, 9), { width: 576, height: 624, dpr: 3 })
})
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
node --test a3-front/a3-front/electron/pet-renderer.test.mjs
```

Expected: FAIL because `canvasBackingSize` and `createInteractionController` are not exported.

- [ ] **Step 3: Implement the minimal pure helpers**

Add:

```javascript
export function canvasBackingSize(cell, value) {
  const dpr = Math.min(Math.max(Number(value) || 1, 1), 3)
  return {
    width: Math.round(cell.width * dpr),
    height: Math.round(cell.height * dpr),
    dpr,
  }
}

export function createInteractionController({ onState, durationFor, setTimer = setTimeout, clearTimer = clearTimeout }) {
  let timer = null
  return {
    play(state) {
      if (timer !== null) clearTimer(timer)
      onState(state)
      timer = setTimer(() => {
        timer = null
        onState(null)
      }, durationFor(state))
    },
    cancel() {
      if (timer !== null) clearTimer(timer)
      timer = null
      onState(null)
    },
  }
}
```

Use the controller inside `startPetRenderer`. In `drawFrame`, calculate one immutable backing size, assign bitmap width/height only when changed, call `context.resetTransform()` when available, clear with identity coordinates, then apply the DPR transform before drawing:

```javascript
const target = canvasBackingSize(payload.pet.cell, window.devicePixelRatio)
if (canvas.width !== target.width || canvas.height !== target.height) {
  canvas.width = target.width
  canvas.height = target.height
}
context.resetTransform?.()
context.clearRect(0, 0, canvas.width, canvas.height)
context.setTransform(target.dpr, 0, 0, target.dpr, 0, 0)
```

- [ ] **Step 4: Run tests and verify GREEN**

Run the Step 2 command. Expected: all pet renderer tests pass.

- [ ] **Step 5: Commit**

```powershell
git add -- a3-front/a3-front/electron/pet/pet-renderer.js a3-front/a3-front/electron/pet-renderer.test.mjs
git commit -m "fix: stabilize pet click rendering"
```

### Task 2: Prove clicks and drags never resize the pet window

**Files:**
- Modify: `a3-front/a3-front/electron/pet-controller.test.mjs`
- Modify only if the test exposes a defect: `a3-front/a3-front/electron/pet-controller.mjs`

- [ ] **Step 1: Add a failing window-size invariant test**

Extend the fake BrowserWindow fixture and assert 100 begin/move/end cycles preserve width, height, and scale:

```javascript
test('repeated click-like drags preserve pet dimensions and scale', async () => {
  const fixture = await preparedController({ scale: 1 })
  const before = fixture.window.getBounds()
  for (let index = 0; index < 100; index += 1) {
    fixture.controller.beginDrag({ screenX: 500, screenY: 300 })
    await fixture.controller.moveDrag({ screenX: 500, screenY: 300 })
    await fixture.controller.endDrag()
  }
  assert.deepEqual(fixture.window.getBounds(), before)
  assert.equal(fixture.controller.snapshot().settings.scale, 1)
})
```

- [ ] **Step 2: Run the test and inspect the evidence**

Run:

```powershell
node --test a3-front/a3-front/electron/pet-controller.test.mjs
```

Expected: the new test either fails with a changed bound, identifying the controller defect, or passes and proves the root cause is renderer-only. Do not change controller code if it passes.

- [ ] **Step 3: If RED, preserve drag dimensions from the live window**

The only allowed controller fix is to freeze the starting size and change position only:

```javascript
drag = {
  screenX: point.screenX,
  screenY: point.screenY,
  bounds: { ...petWindow.getBounds() },
  directionState: null,
}
```

`moveDrag` must continue calling `setPosition`, never `setBounds`, for ordinary drag movement.

- [ ] **Step 4: Verify GREEN**

Run the Step 2 command. Expected: all pet controller tests pass and no test observes width/height growth.

- [ ] **Step 5: Commit the test and any proven fix**

```powershell
git add -- a3-front/a3-front/electron/pet-controller.test.mjs a3-front/a3-front/electron/pet-controller.mjs
git commit -m "test: lock pet window dimensions"
```

### Task 3: Raise local and backend file limits to 500 MiB

**Files:**
- Modify: `a3-front/a3-front/electron/knowledge-import.test.mjs`
- Modify: `a3-front/a3-front/electron/knowledge-import.mjs`
- Modify: `backend/tests/knowledge/test_schemas.py`
- Modify: `backend/knowledge/schemas.py`

- [ ] **Step 1: Write Electron boundary tests**

Add sparse-file metadata tests or inject `stat` into the importer fixture so a 500 MiB file is accepted and 500 MiB + 1 is rejected:

```javascript
test('accepts a single knowledge file up to 500 MiB', async () => {
  const importer = fixture({ fileSize: 500 * 1024 * 1024 })
  const result = await importer.importPaths(['C:\\教材\\数学.pdf'])
  assert.equal(result[0].byte_size, 500 * 1024 * 1024)
})

test('rejects a single knowledge file above 500 MiB', async () => {
  const importer = fixture({ fileSize: 500 * 1024 * 1024 + 1 })
  await assert.rejects(
    importer.importPaths(['C:\\教材\\数学.pdf']),
    error => error.code === 'KNOWLEDGE_FILE_TOO_LARGE' && /500/.test(error.message),
  )
})
```

- [ ] **Step 2: Write backend schema boundary tests**

```python
def test_import_manifest_accepts_500_mib():
    value = valid_manifest(byte_size=500 * 1024 * 1024)
    assert ImportManifest.model_validate(value).byte_size == 500 * 1024 * 1024

def test_import_manifest_rejects_more_than_500_mib():
    with pytest.raises(ValidationError):
        ImportManifest.model_validate(valid_manifest(byte_size=500 * 1024 * 1024 + 1))
```

- [ ] **Step 3: Run both test sets and verify RED**

```powershell
node --test a3-front/a3-front/electron/knowledge-import.test.mjs
python -m pytest backend/tests/knowledge/test_schemas.py -q
```

Expected: the 500 MiB acceptance tests fail because both current limits are 100 MiB.

- [ ] **Step 4: Make the limits consistent**

Use the same binary unit in both files:

```javascript
const MAX_FILE_BYTES = 500 * 1024 * 1024
const MAX_BATCH_BYTES = 500 * 1024 * 1024
```

```python
MAX_FILE_BYTES = 500 * 1024 * 1024
MAX_BATCH_BYTES = 500 * 1024 * 1024
```

Change the Electron message to `单个文件不能超过 500 MiB。`; retain the 500 MiB batch total.

- [ ] **Step 5: Run tests and verify GREEN**

Run the Step 3 commands. Expected: all targeted tests pass.

- [ ] **Step 6: Commit**

```powershell
git add -- a3-front/a3-front/electron/knowledge-import.mjs a3-front/a3-front/electron/knowledge-import.test.mjs backend/knowledge/schemas.py backend/tests/knowledge/test_schemas.py
git commit -m "fix: support 500 MiB knowledge files"
```

### Task 4: Make preview and local-reader actions explicit

**Files:**
- Modify: `a3-front/a3-front/src/components/knowledge/DocumentInspector.test.ts`
- Modify: `a3-front/a3-front/src/components/knowledge/DocumentInspector.vue`
- Modify: `a3-front/a3-front/src/views/KnowledgeLibrary.test.ts`
- Modify: `a3-front/a3-front/src/views/KnowledgeLibrary.vue`
- Modify only if needed: `a3-front/a3-front/electron/knowledge-controller.test.mjs`
- Modify only if needed: `a3-front/a3-front/electron/knowledge-controller.mjs`

- [ ] **Step 1: Write failing component tests**

For a completed PDF, require separate `preview` and `open` events:

```typescript
it('offers preview and system-reader actions for completed documents', async () => {
  const wrapper = mount(DocumentInspector, { props: { document: completedPdf, desktopAvailable: true } })
  await wrapper.get('[aria-label="预览 教材.pdf"]').trigger('click')
  await wrapper.get('[aria-label="用本地阅读器打开 教材.pdf"]').trigger('click')
  expect(wrapper.emitted('preview')?.[0]).toEqual([completedPdf.id])
  expect(wrapper.emitted('open')?.[0]).toEqual([completedPdf.id])
})
```

- [ ] **Step 2: Run the component tests and verify RED**

```powershell
Set-Location a3-front/a3-front
npx vitest run src/components/knowledge/DocumentInspector.test.ts src/views/KnowledgeLibrary.test.ts
```

Expected: FAIL because only the old “打开只读副本” action exists.

- [ ] **Step 3: Implement the minimal UI contract**

Add two buttons and events:

```vue
<button v-if="document.status === 'COMPLETED'" :aria-label="`预览 ${document.display_name}`" @click="$emit('preview', document.id)">预览</button>
<button v-if="desktopAvailable && document.status === 'COMPLETED'" :aria-label="`用本地阅读器打开 ${document.display_name}`" @click="$emit('open', document.id)">用本地阅读器打开</button>
```

In `KnowledgeLibrary.vue`, `previewDocument` uses the existing routed locator and `openKnowledgeSource`; the system-reader action uses the same controlled readonly-copy path until a renderer-native PDF preview is proven stable. Show a message explaining the fallback:

```typescript
async function previewDocument(id: number) {
  const result = await backendApi.openKnowledgeSource(id, routedLocator.value || { type: 'paragraph', start: 1, end: 1 })
  if (result.mode === 'readonly-copy') ElMessage.success('已用本地阅读器打开只读预览。')
}
```

- [ ] **Step 4: Verify controller safety remains intact**

```powershell
node --test a3-front/a3-front/electron/knowledge-controller.test.mjs
Set-Location a3-front/a3-front
npx vitest run src/components/knowledge/DocumentInspector.test.ts src/views/KnowledgeLibrary.test.ts
```

Expected: controller still creates a UUID-scoped, read-only copy without returning its path; component/page tests pass.

- [ ] **Step 5: Commit**

```powershell
git add -- a3-front/a3-front/src/components/knowledge/DocumentInspector.vue a3-front/a3-front/src/components/knowledge/DocumentInspector.test.ts a3-front/a3-front/src/views/KnowledgeLibrary.vue a3-front/a3-front/src/views/KnowledgeLibrary.test.ts
git commit -m "feat: expose knowledge preview actions"
```

### Task 5: Verify real files, full regressions, and desktop packaging

**Files:**
- Modify: `codex/AI模型任务队列.md`
- Generated/ignored: `a3-front/a3-front/desktop-backend/`
- Generated/ignored: `a3-front/a3-front/release/`

- [ ] **Step 1: Run the real import reproduction**

Use `C:\Users\123\Desktop\作业\教材` and require both PDFs to pass Electron validation and object copy in one batch. Record names, exact byte sizes, hashes, elapsed time and manifest count without logging document contents.

Run the existing `.tmp/import-repro.mjs` after updating it only to point at the current worktree modules. Expected: two manifests, total below 500 MiB, no `KNOWLEDGE_FILE_TOO_LARGE`.

- [ ] **Step 2: Run focused and full tests**

```powershell
node --test a3-front/a3-front/electron/pet-renderer.test.mjs a3-front/a3-front/electron/pet-controller.test.mjs a3-front/a3-front/electron/knowledge-import.test.mjs a3-front/a3-front/electron/knowledge-controller.test.mjs
python -m pytest backend/tests/knowledge -q
Set-Location a3-front/a3-front
npm test
npm run type-check
npm run build:desktop
```

Expected: all commands exit 0.

- [ ] **Step 3: Rebuild the packaged backend and unpacked app**

Run the existing backend packaging command documented by the repository, copy the verified backend into `desktop-backend`, then:

```powershell
Set-Location a3-front/a3-front
npm run desktop:pack
```

Expected: `release/win-unpacked/智学协作台.exe` exists and packages the updated knowledge limits.

- [ ] **Step 4: Run packaged lifecycle and manual click evidence**

Launch the unpacked app with isolated `A3_ELECTRON_USER_DATA_DIR`. Confirm backend ready/stop logs, exit code 0 and zero residual processes. In a normal run, click the pet continuously for at least 30 seconds and record before/after BrowserWindow bounds, DPR, canvas bitmap size and client size; all four dimensions must remain constant.

- [ ] **Step 5: Update the queue and commit acceptance evidence**

Mark S-031 complete only after real files, full regression and packaged run pass. Record exact counts and hashes in `codex/AI模型任务队列.md`, then:

```powershell
git add -- codex/AI模型任务队列.md
git commit -m "test: verify desktop textbook import"
```

## Self-Review

- Spec coverage: Tasks 1–2 cover renderer and window invariants; Task 3 covers synchronized 500 MiB limits; Task 4 covers explicit preview/read actions; Task 5 covers the two user PDFs and packaged desktop verification.
- Type consistency: `canvasBackingSize`, `createInteractionController`, `preview`, `open`, `MAX_FILE_BYTES` and `MAX_BATCH_BYTES` retain the same names throughout.
- Scope: no whole-file renderer buffering, arbitrary filesystem access or unrelated pet feature is introduced.

