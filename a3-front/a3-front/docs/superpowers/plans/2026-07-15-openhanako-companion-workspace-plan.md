# Openhanako Companion Workspace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 A3 前端从管理后台式布局改造成暖色、三栏、陪伴式学习工作台，同时保持现有真实后端流程和 Electron 安全边界。

**Architecture:** 保留 `AppLayout` 作为唯一应用壳，在其内部拆出纯展示组件 `ConversationRail` 与 `DeskPanel`。`SmartTutor` 继续负责消息/SSE 业务，仅调整欢迎态和视觉层级；Pinia store 仍是唯一后端数据来源，便签只在前端本地保存。

**Tech Stack:** Vue 3 `<script setup>`, TypeScript, Pinia, Element Plus, Vitest + Vue Test Utils, SCSS。

---

### Task 1: 为三栏工作台写行为测试

**Files:**
- Create: `a3-front/a3-front/src/components/workspace/ConversationRail.test.ts`
- Create: `a3-front/a3-front/src/components/workspace/DeskPanel.test.ts`

- [ ] **Step 1: 写失败测试**

```ts
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import ConversationRail from './ConversationRail.vue'

describe('ConversationRail', () => {
  it('shows the active space and emits a new-session action', async () => {
    const wrapper = mount(ConversationRail, {
      props: { sessionLabel: '一次函数 · 第 2 次学习', activePath: '/tutor' },
      global: { stubs: { RouterLink: { template: '<a><slot /></a>' }, ElIcon: { template: '<i><slot /></i>' }, ElButton: { template: '<button @click="$emit(\'click\')"><slot /></button>' } } },
    })
    expect(wrapper.text()).toContain('一次函数 · 第 2 次学习')
    await wrapper.get('[aria-label="新学习会话"]').trigger('click')
    expect(wrapper.emitted('new-session')).toHaveLength(1)
  })
})
```

```ts
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import DeskPanel from './DeskPanel.vue'

describe('DeskPanel', () => {
  it('keeps a short note in local storage and emits a suggested prompt', async () => {
    localStorage.clear()
    const wrapper = mount(DeskPanel, {
      props: { nextAction: { action: 'START_PRACTICE', reason: '先做一道热身题', knowledge_point: '一次函数', recommended_difficulty: '基础', suggested_request: '给我一道一次函数热身题' }, mastery: 0.6, resourceCount: 1 },
      global: { stubs: { ElButton: { template: '<button @click="$emit(\'click\')"><slot /></button>' }, ElProgress: true } },
    })
    const note = wrapper.get('textarea')
    await note.setValue('今晚复习斜率')
    expect(localStorage.getItem('a3-companion-note')).toBe('今晚复习斜率')
    await wrapper.get('[data-test="suggested-action"]').trigger('click')
    expect(wrapper.emitted('use-suggestion')?.[0]).toEqual(['给我一道一次函数热身题'])
  })
})
```

- [ ] **Step 2: 运行测试确认失败**

Run: `npm run test -- --run src/components/workspace/ConversationRail.test.ts src/components/workspace/DeskPanel.test.ts`

Expected: FAIL because the two components do not exist yet.

### Task 2: 实现左侧空间导航和右侧书桌面板

**Files:**
- Create: `a3-front/a3-front/src/components/workspace/ConversationRail.vue`
- Create: `a3-front/a3-front/src/components/workspace/DeskPanel.vue`

- [ ] **Step 1: 实现 ConversationRail**

组件接收 `sessionLabel`, `sessionState`, `activePath` 和 `compact`，渲染新会话按钮、`RouterLink` 空间列表、最近会话占位和未来账号插槽；点击按钮只发出 `new-session`，不直接改 store。

- [ ] **Step 2: 实现 DeskPanel**

组件接收 `nextAction`, `mastery`, `resourceCount`, `sources`，通过 `ref` 加载 `localStorage` 中 `a3-companion-note`，输入时截断到 120 字并保存；推荐按钮发出 `use-suggestion`。无数据时显示“今天的书桌还很安静”。

- [ ] **Step 3: 运行测试确认通过**

Run: `npm run test -- --run src/components/workspace/ConversationRail.test.ts src/components/workspace/DeskPanel.test.ts`

Expected: PASS。

### Task 3: 把新组件接入 AppLayout

**Files:**
- Modify: `a3-front/a3-front/src/layouts/AppLayout.vue`
- Modify: `a3-front/a3-front/src/layouts/AppLayout.test.ts`

- [ ] **Step 1: 先扩展失败测试**

断言布局包含 `[data-test="conversation-rail"]`、`[data-test="desk-panel"]`，并且点击新会话后路由跳到 `/tutor`。

- [ ] **Step 2: 实现最小接线**

将原固定 `aside.sidebar` 替换为 `ConversationRail`，在 `main-content` 后加入 `DeskPanel`；从 `backend.session`、`backend.nextAction`、`backend.progress`、`backend.resources` 和 `backend.sources` 传入数据。`DeskPanel` 的 `use-suggestion` 通过 `router.push({ path: '/tutor', query: { prompt } })` 复用现有输入流程。

- [ ] **Step 3: 运行布局回归**

Run: `npm run test -- --run src/layouts/AppLayout.test.ts`

Expected: PASS，且原有后端退出与模型设置自动跳转断言保持通过。

### Task 4: 重做 SmartTutor 欢迎态（保持 SSE 业务不变）

**Files:**
- Modify: `a3-front/a3-front/src/views/SmartTutor.vue`
- Modify: `a3-front/a3-front/src/views/SmartTutor.test.ts`

- [ ] **Step 1: 写欢迎态行为测试**

新增断言：空会话显示“今天想一起学点什么？”、角色胶囊“学习伙伴”、工作空间文本和三个 starter；点击 starter 会填充编辑器；现有发送/错误/取消测试不删。

- [ ] **Step 2: 实现欢迎态**

将欢迎区域改为中心留白布局，保留现有 `starters` 数组和 `editor` 绑定；增加静态 `companionId = 'study-companion'` 和 `accountSlot` 注释边界，不新增账号逻辑。消息列表、SSE 事件处理、失败重编辑代码保持原样。

- [ ] **Step 3: 运行 SmartTutor 测试**

Run: `npm run test -- --run src/views/SmartTutor.test.ts`

Expected: PASS。

### Task 5: 应用暖色纸张视觉与响应式规则

**Files:**
- Modify: `a3-front/a3-front/src/styles/global.scss`
- Modify: `a3-front/a3-front/src/views/SmartTutor.vue`
- Modify: `a3-front/a3-front/src/layouts/AppLayout.vue`

- [ ] **Step 1: 统一设计变量**

将背景、边框、阴影、圆角和字体变量集中到 `:root`；主背景使用米白 `#f4efe6`，墨色 `#403a35`，蓝绿 `#6c9aa0`，便签琥珀 `#f4e6bd`。避免高饱和渐变和大面积深色。

- [ ] **Step 2: 实现三栏尺寸与窄屏折叠**

桌面端使用 `grid-template-columns: 220px minmax(0, 1fr) 290px`；`max-width: 1100px` 时隐藏右栏并提供按钮打开；`760px` 以下隐藏左右栏、启用抽屉、保持 composer 固定在内容底部且不出现横向滚动。

- [ ] **Step 3: 保留 Electron 拖拽区安全性**

仅顶栏品牌空白区使用 `-webkit-app-region: drag`，所有按钮、输入框和链接设置 `no-drag`；不渲染动态端口、令牌或密钥。

### Task 6: 全量验证并记录 T-030

**Files:**
- Modify: `codex/AI模型任务队列.md`
- Modify: `a3-front/a3-front/README.md`（若需补充新工作台入口说明）

- [ ] **Step 1: 运行前端测试**

Run: `npm run test`

Expected: Electron Node tests 与 Vitest 全部通过，退出码 0。

- [ ] **Step 2: 运行 Web/桌面构建**

Run: `npm run build` and `npm run build:desktop`

Expected: 两条命令退出码 0，Vite 无新的大包告警。

- [ ] **Step 3: 浏览器验收**

启动 Vite，检查 `/tutor`、`/dashboard` 和 `/model-settings`；在 1440px 与 375px 宽度各截图一次，确认三栏逻辑、欢迎态、输入框、导航抽屉和模型设置自动引导可用。

- [ ] **Step 4: 更新任务记录并提交**

在队列中记录修改文件、测试结果和视觉验收；执行 `git diff --check`、`git status --short` 后提交：

```bash
git add a3-front/a3-front/src codex/AI模型任务队列.md
git commit -m "feat: add companion learning workspace"
```

