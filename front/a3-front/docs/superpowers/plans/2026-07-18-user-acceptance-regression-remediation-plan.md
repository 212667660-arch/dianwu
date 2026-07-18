# S-039 User Acceptance Regression Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复练习答案控件重叠、单收藏闪烁、学习诊断说明不清和墨团连续点击保持放大姿态，并完成桌面发布回归。

**Architecture:** 四项缺陷保持独立边界：练习页只调整答题表单；知识库为单收藏增加局部乐观更新；学习助手保留安全错误码并渲染专用诊断恢复卡；桌宠交互控制器对同状态重复事件去重。后端协议和数据库模型不变，最终通过统一桌面发布门验收。

**Tech Stack:** Vue 3、TypeScript、Pinia、Element Plus、Vitest、Electron、Node test runner、Electron Builder。

---

### Task 1: 将练习题收敛为单一答案入口

**Files:**
- Create: `src/views/Assessment.test.ts`
- Modify: `src/views/Assessment.vue`

- [ ] **Step 1: 写出失败的组件测试**

在 `Assessment.test.ts` 中 mock `useBackendStore()`，提供一条题目并验证只有一个文本输入、没有数字输入，点击提交后第三个参数固定为零：

```ts
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, expect, it, vi } from 'vitest'

const store = vi.hoisted(() => ({
  resources: [{
    id: 1, topic: '一次函数', quality_score: 100,
    questions: [{ id: 7, ordinal: 1, difficulty: '基础', prompt: '当 y=2x+1 且 x=2 时，y 等于多少？' }],
  }],
  reviews: [], mistakes: [], refreshSession: vi.fn(),
  submitAnswer: vi.fn().mockResolvedValue({
    correct: true, expected_answer: '5', explanation: '代入计算', feedback: '回答正确',
    mastery_score: 0.8, mastery_label: 'PROFICIENT', next_review_at: '', error_type: null,
  }),
}))

vi.mock('@/stores/backend', () => ({ useBackendStore: () => store }))
vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }) }))

import Assessment from './Assessment.vue'

beforeEach(() => vi.clearAllMocks())

it('uses one answer field and submits without a manual hint counter', async () => {
  const wrapper = mount(Assessment)
  const answer = wrapper.get('[data-testid="assessment-answer-7"] input')
  await answer.setValue('5')

  expect(wrapper.find('.el-input-number').exists()).toBe(false)
  expect(wrapper.get('[data-testid="assessment-submit-7"]').isVisible()).toBe(true)

  await wrapper.get('[data-testid="assessment-submit-7"]').trigger('click')
  await flushPromises()
  expect(store.submitAnswer).toHaveBeenCalledWith(7, '5', 0)
})
```

- [ ] **Step 2: 运行测试确认 RED**

Run:

```powershell
npx vitest run src/views/Assessment.test.ts
```

Expected: FAIL，因为页面仍存在 `.el-input-number`，且没有新的 `data-testid`。

- [ ] **Step 3: 实现最小修复**

在 `Assessment.vue`：

```vue
<div class="answer-row">
  <el-input
    v-model="answers[row.question.id]"
    :data-testid="`assessment-answer-${row.question.id}`"
    placeholder="输入你的答案"
    @keyup.enter="submit(row.question.id)"
  />
  <el-button
    :data-testid="`assessment-submit-${row.question.id}`"
    type="primary"
    :loading="submitting === row.question.id"
    @click="submit(row.question.id)"
  >提交</el-button>
</div>
```

删除 `hints` reactive，并将提交调用改为：

```ts
results[questionId] = await backend.submitAnswer(questionId, answer, 0)
```

样式改为：

```scss
.answer-row { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 8px; margin-top: 13px; }
.answer-row :deep(.el-button) { min-width: 82px; }
```

- [ ] **Step 4: 运行测试确认 GREEN**

```powershell
npx vitest run src/views/Assessment.test.ts
```

Expected: 1 passed。

- [ ] **Step 5: 提交 Task 1**

```powershell
git add src/views/Assessment.vue src/views/Assessment.test.ts
git commit -m "fix: simplify assessment answer entry"
```

### Task 2: 单收藏使用局部乐观更新

**Files:**
- Modify: `src/views/KnowledgeLibrary.vue`
- Modify: `src/views/KnowledgeLibrary.test.ts`
- Modify: `src/components/knowledge/DocumentGrid.vue`
- Modify: `src/components/knowledge/DocumentGrid.test.ts`

- [ ] **Step 1: 写出失败的页面测试**

在 `KnowledgeLibrary.test.ts` 增加：

```ts
it('toggles one favorite without changing selection or reloading the document list', async () => {
  store.knowledgeDocuments = [{ ...store.knowledgeDocuments[0], favorite: false, deleted_at: null, collection_ids: [3], tags: [] }]
  store.bulkKnowledgeDocuments.mockResolvedValueOnce({ items: [{ document_id: 9, ok: true, code: null }] })
  const wrapper = mount(KnowledgeLibrary, { global: { stubs: { ElDrawer: { template: '<div><slot /></div>' } } } })
  await flushPromises()
  apiMock.knowledgeDocuments.mockClear()

  await wrapper.get('[data-testid="favorite-document-9"]').trigger('click')
  expect(wrapper.get('[data-testid="bulk-selection-count"]').text()).toContain('0')
  expect(wrapper.get('[data-testid="favorite-document-9"]').text()).toBe('★')
  await flushPromises()

  expect(store.bulkKnowledgeDocuments).toHaveBeenCalledWith({
    action: 'favorite', document_ids: [9], collection_ids: [], tags: [], favorite: true,
  })
  expect(apiMock.knowledgeDocuments).not.toHaveBeenCalled()
})
```

再增加失败回滚测试：请求 reject 后星号恢复为 `☆`，选择数量仍为零。

- [ ] **Step 2: 运行页面测试确认 RED**

```powershell
npx vitest run src/views/KnowledgeLibrary.test.ts
```

Expected: FAIL，因为现实现会把选择数改为 1/0，并调用 `knowledgeDocuments()` 刷新。

- [ ] **Step 3: 实现单收藏局部更新**

在 `KnowledgeLibrary.vue` 增加：

```ts
const favoritePendingIds = ref<number[]>([])

async function toggleFavorite(id: number, favorite: boolean) {
  if (favoritePendingIds.value.includes(id)) return
  const index = backend.knowledgeDocuments.findIndex(item => item.id === id)
  if (index < 0) return
  const previous = backend.knowledgeDocuments[index]
  favoritePendingIds.value = [...favoritePendingIds.value, id]
  backend.knowledgeDocuments[index] = { ...previous, favorite }
  try {
    const result = await backend.bulkKnowledgeDocuments({
      action: 'favorite', document_ids: [id], collection_ids: [], tags: [], favorite,
    })
    if (!result.items.some(item => item.document_id === id && item.ok)) throw new Error('收藏状态未保存，请重试。')
    if (favoriteOnly.value && !favorite) {
      backend.knowledgeDocuments = backend.knowledgeDocuments.filter(item => item.id !== id)
      if (selectedDocumentId.value === id) selectedDocumentId.value = backend.knowledgeDocuments[0]?.id || null
    }
  } catch (error) {
    const rollbackIndex = backend.knowledgeDocuments.findIndex(item => item.id === id)
    if (rollbackIndex >= 0) backend.knowledgeDocuments[rollbackIndex] = previous
    ElMessage.error(errorMessage(error))
  } finally {
    favoritePendingIds.value = favoritePendingIds.value.filter(item => item !== id)
  }
}
```

将 pending IDs 传入 `DocumentGrid`：

```vue
<DocumentGrid :favorite-pending-ids="favoritePendingIds" ... />
```

在 `DocumentGrid.vue` 增加 prop，并在星号按钮使用：

```vue
:disabled="favoritePendingIds.includes(item.id)"
:aria-busy="favoritePendingIds.includes(item.id)"
```

- [ ] **Step 4: 补充 DocumentGrid pending 测试并运行 GREEN**

验证 pending ID 对应按钮 disabled，其他卡片不受影响：

```powershell
npx vitest run src/components/knowledge/DocumentGrid.test.ts src/views/KnowledgeLibrary.test.ts
```

Expected: 全部 passed。

- [ ] **Step 5: 提交 Task 2**

```powershell
git add src/views/KnowledgeLibrary.vue src/views/KnowledgeLibrary.test.ts src/components/knowledge/DocumentGrid.vue src/components/knowledge/DocumentGrid.test.ts
git commit -m "fix: update document favorites without toolbar flicker"
```

### Task 3: 为学习诊断错误提供解释和可操作入口

**Files:**
- Modify: `src/views/SmartTutor.vue`
- Modify: `src/views/SmartTutor.test.ts`

- [ ] **Step 1: 写出失败的诊断错误测试**

在 `SmartTutor.test.ts` 让 `streamChat` 发出：

```ts
onEvent({ event: 'error', code: 'RESOURCE_NOT_READY', message: '会话尚未完成诊断，请先继续诊断。' })
```

断言：

```ts
expect(wrapper.get('[data-testid="learning-diagnosis-help"]').text()).toContain('学习诊断')
expect(wrapper.text()).toContain('学习目标、基础和薄弱点')
expect(wrapper.get('[data-testid="continue-learning-diagnosis"]').text()).toContain('继续学习诊断')
```

点击按钮后断言 textarea 包含“继续完成学习诊断”。

- [ ] **Step 2: 运行 SmartTutor 测试确认 RED**

```powershell
npx vitest run src/views/SmartTutor.test.ts
```

Expected: FAIL，因为现有页面没有错误码状态和诊断专用卡。

- [ ] **Step 3: 保存错误码并渲染专用卡**

在 `SmartTutor.vue` 增加：

```ts
const streamErrorCode = ref('')
const isLearningDiagnosisError = computed(() => ['RESOURCE_NOT_READY', 'PROFILE_MISSING'].includes(streamErrorCode.value))
const diagnosisCompleted = computed(() => backend.session?.state === 'PROFILED')

function recoverLearningDiagnosis() {
  streamError.value = ''
  streamErrorCode.value = ''
  streamText.value = ''
  editor.value = diagnosisCompleted.value
    ? failedMessage.value
    : '我想继续完成学习诊断，请根据我的学习目标、当前基础和薄弱点继续提问。'
}
```

流事件错误保存 `event.code`，catch 中对 `DesktopApiError` 保存 `error.code`；每次新发送和普通恢复时清空错误码。

模板将通用错误卡拆分为：

```vue
<div v-if="streamError && isLearningDiagnosisError" class="stream-error diagnosis-help" data-testid="learning-diagnosis-help" role="alert">
  <div>
    <strong>需要先完成学习诊断</strong>
    <p>学习诊断不是电脑故障检测，而是画像 Agent 通过几轮对话了解你的学习目标、当前基础和薄弱点。</p>
    <p>{{ diagnosisCompleted ? '当前画像已经完成，可以重新尝试刚才的请求。' : '请先继续回答学习助手的问题，画像完成后即可生成练习和学习资源。' }}</p>
  </div>
  <el-button data-testid="continue-learning-diagnosis" text type="primary" @click="recoverLearningDiagnosis">
    {{ diagnosisCompleted ? '重新尝试刚才请求' : '继续学习诊断' }}
  </el-button>
</div>
<div v-else-if="streamError" class="stream-error" role="alert">...</div>
```

- [ ] **Step 4: 运行诊断与普通错误回归确认 GREEN**

```powershell
npx vitest run src/views/SmartTutor.test.ts
```

Expected: 所有 SmartTutor 测试 passed，既有普通错误仍显示“重新编辑”。

- [ ] **Step 5: 提交 Task 3**

```powershell
git add src/views/SmartTutor.vue src/views/SmartTutor.test.ts
git commit -m "fix: explain and recover learning diagnosis errors"
```

### Task 4: 阻止墨团同一点击动画被无限续期

**Files:**
- Modify: `electron/pet/pet-renderer.js`
- Modify: `electron/pet-renderer.test.mjs`

- [ ] **Step 1: 写出失败的交互寿命测试**

在 `pet-renderer.test.mjs` 增加：

```js
test('repeated identical interactions cannot extend the current animation lifetime', () => {
  const timers = new Map()
  let nextId = 0
  let clearCount = 0
  const controller = createInteractionController({
    onState: () => {},
    durationFor: () => 400,
    setTimer: callback => { const id = ++nextId; timers.set(id, callback); return id },
    clearTimer: id => { clearCount += 1; timers.delete(id) },
  })

  controller.play('jumping')
  for (let index = 0; index < 100; index += 1) controller.play('jumping')

  assert.equal(nextId, 1)
  assert.equal(clearCount, 0)
  assert.equal(timers.size, 1)
})
```

- [ ] **Step 2: 运行 Electron 测试确认 RED**

```powershell
node --test electron/pet-renderer.test.mjs
```

Expected: FAIL，当前实现会创建 101 个 timer 并清除 100 次。

- [ ] **Step 3: 实现同状态交互去重**

修改 `createInteractionController()`：

```js
let timer = null
let activeState = null
return {
  play(state) {
    if (timer !== null && activeState === state) return false
    if (timer !== null) clearTimer(timer)
    activeState = state
    onState(state)
    timer = setTimer(() => {
      timer = null
      activeState = null
      onState(null)
    }, durationFor(state))
    return true
  },
  cancel() {
    if (timer !== null) clearTimer(timer)
    timer = null
    activeState = null
    onState(null)
  },
}
```

- [ ] **Step 4: 运行 pet renderer/controller 回归确认 GREEN**

```powershell
node --test electron/pet-renderer.test.mjs electron/pet-controller.test.mjs
```

Expected: 全部 passed。

- [ ] **Step 5: 提交 Task 4**

```powershell
git add electron/pet/pet-renderer.js electron/pet-renderer.test.mjs
git commit -m "fix: bound repeated Motuan interactions"
```

### Task 5: 完整回归、桌面验收和队列收尾

**Files:**
- Modify: `codex/AI模型任务队列.md`
- Generated/verify only: `release/`

- [ ] **Step 1: 运行定向测试**

```powershell
node --test electron/pet-renderer.test.mjs electron/pet-controller.test.mjs
npx vitest run src/views/Assessment.test.ts src/components/knowledge/DocumentGrid.test.ts src/views/KnowledgeLibrary.test.ts src/views/SmartTutor.test.ts
```

- [ ] **Step 2: 运行完整桌面与前端测试**

```powershell
npm test
npm run build:desktop
```

Expected: Electron/Node、Vitest、vue-tsc 和 Vite 均退出码 0。

- [ ] **Step 3: 运行隔离后端回归**

从仓库根目录：

```powershell
$env:A3_DATA_DIR = Join-Path $env:TEMP ("a3-s039-" + [guid]::NewGuid().ToString("N"))
E:\软件杯\.venv\Scripts\python.exe -m pytest -q backend
```

Expected: 559 passed、7 skipped 或更高通过数，0 failed。

- [ ] **Step 4: 重新打包并执行真实桌面生命周期验收**

```powershell
npm run desktop:pack
```

使用 `A3_ELECTRON_TEST_MODE=1` 和全新 `A3_ELECTRON_USER_DATA_DIR` 启动 `release/win-unpacked/智学协作台.exe`，确认退出码 0、tray/backend ready/backend stop/test-mode exit 四项日志齐全、数据库创建成功、残留进程 0。

- [ ] **Step 5: 更新队列和提交验收**

将 S-039 改为完成，在完成记录中写入根因、测试计数、构建与生命周期证据：

```powershell
git add codex/AI模型任务队列.md
git commit -m "chore: record user acceptance regression fixes"
```

- [ ] **Step 6: 最终差异检查**

```powershell
git diff --check
git status --short --branch
```

只允许约定保留的 `.tmp/` 与 `dist-s033*` 未跟踪目录存在。
