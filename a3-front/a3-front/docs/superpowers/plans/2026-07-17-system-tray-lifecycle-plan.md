# System Tray Lifecycle Implementation Plan

> 状态：3 个任务均已按 TDD 实施并完成 Windows 打包验收。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为智学协作台增加始终可见的 Windows 系统托盘、主窗口恢复入口和能够完整回收后端/桌宠的退出入口。

**Architecture:** 新建纯主进程托盘控制器，将 Electron `Tray`/`Menu` 与窗口显示、退出请求通过依赖注入隔离并单元测试。`main.mjs` 负责创建唯一控制器，主窗口关闭时仅在托盘有效且应用未退出时隐藏；托盘失败则关闭即退出。已有 `before-quit` 继续统一清理后端、知识任务和桌宠。

**Tech Stack:** Electron 32, Node.js test runner, JavaScript ESM, Windows NSIS

---

## File Structure

- Create: `electron/tray-lifecycle.mjs` — 托盘菜单、窗口恢复、退出请求和关闭动作判定。
- Create: `electron/tray-lifecycle.test.mjs` — 使用假 Tray/Menu/BrowserWindow 验证行为。
- Create: `electron/assets/tray-icon.png` — 32×32 本地透明托盘图标。
- Modify: `electron/main.mjs` — 创建/销毁托盘并接入主窗口与应用生命周期。
- Modify: `electron/runtime.test.mjs` — 固定主进程必须接入托盘且测试模式仍安全退出。
- Modify: `package.json` — 把托盘测试加入完整 Node 测试入口。
- Modify: `codex/AI模型任务队列.md` — 记录验证和发布结果。

### Task 1: Implement a testable tray controller

**Files:**
- Create: `a3-front/a3-front/electron/tray-lifecycle.test.mjs`
- Create: `a3-front/a3-front/electron/tray-lifecycle.mjs`

- [ ] **Step 1: Write failing controller tests**

Tests construct fake `Tray`, `Menu` and window objects and assert:

```javascript
test('tray click restores and focuses the main window', () => {
  const window = fakeWindow({ minimized: true, visible: false })
  const controller = createTrayController({
    Tray: FakeTray,
    Menu: FakeMenu,
    icon: { isEmpty: () => false },
    getMainWindow: () => window,
    requestQuit: () => {},
  })
  controller.tray.emit('click')
  assert.deepEqual(window.calls, ['restore', 'show', 'focus'])
})

test('tray exit menu requests one complete application quit', () => {
  let quits = 0
  const controller = fixture({ requestQuit: () => { quits += 1 } })
  controller.menuTemplate.find(item => item.label === '退出智学协作台').click()
  assert.equal(quits, 1)
})

test('main window hides only when a usable tray exists', () => {
  assert.equal(mainWindowCloseAction({ isQuitting: false, hasTray: true }), 'hide')
  assert.equal(mainWindowCloseAction({ isQuitting: false, hasTray: false }), 'quit')
  assert.equal(mainWindowCloseAction({ isQuitting: true, hasTray: true }), 'allow')
})
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
node --test electron/tray-lifecycle.test.mjs
```

Expected: FAIL because `tray-lifecycle.mjs` does not exist.

- [ ] **Step 3: Implement the minimal controller**

`createTrayController` must reject an empty icon, set tooltip/context menu, bind click/double-click to `showMainWindow`, and expose an idempotent `destroy`. `mainWindowCloseAction` returns only `hide`, `quit`, or `allow`.

```javascript
export function mainWindowCloseAction({ isQuitting, hasTray }) {
  if (isQuitting) return 'allow'
  return hasTray ? 'hide' : 'quit'
}

export function showMainWindow(window) {
  if (!window || window.isDestroyed()) return false
  if (window.isMinimized()) window.restore()
  window.show()
  window.focus()
  return true
}
```

- [ ] **Step 4: Run tests and verify GREEN**

Run the Step 2 command. Expected: all tray controller tests pass.

### Task 2: Connect Electron lifecycle and package a visible icon

**Files:**
- Create: `a3-front/a3-front/electron/assets/tray-icon.png`
- Modify: `a3-front/a3-front/electron/main.mjs`
- Modify: `a3-front/a3-front/electron/runtime.test.mjs`
- Modify: `a3-front/a3-front/package.json`

- [ ] **Step 1: Add failing main-process integration assertions**

Extend `runtime.test.mjs` to assert the main process imports `Tray` and `Menu`, creates one tray controller after the main window, routes `second-instance` through controller `show`, handles main-window `close`, destroys the tray in `before-quit`, and logs `tray ready`.

- [ ] **Step 2: Run integration tests and verify RED**

Run:

```powershell
node --test electron/tray-lifecycle.test.mjs electron/runtime.test.mjs
```

Expected: controller tests pass and runtime integration assertion fails because `main.mjs` has no tray wiring.

- [ ] **Step 3: Generate and inspect the local tray icon**

Crop the first 192×208 idle frame from `electron/pets/motuan/spritesheet.webp`, contain it within a transparent 32×32 canvas, and save it as `electron/assets/tray-icon.png`. Verify the file is PNG, 32×32 RGBA and not fully transparent.

- [ ] **Step 4: Wire the lifecycle**

Import `Menu` and `Tray`, create the icon with `nativeImage.createFromPath`, create one tray controller after `createWindow`, and log `tray ready`. The main-window close handler applies:

```javascript
const action = mainWindowCloseAction({
  isQuitting,
  hasTray: Boolean(trayController),
})
if (action === 'hide') {
  event.preventDefault()
  mainWindow?.hide()
} else if (action === 'quit') {
  isQuitting = true
  app.quit()
}
```

The tray exit callback sets `isQuitting=true` before `app.quit()`. `before-quit` destroys the tray and uses existing cleanup. `package.json` adds `electron/tray-lifecycle.test.mjs` to `npm test`.

- [ ] **Step 5: Run tests and verify GREEN**

Run:

```powershell
node --test electron/tray-lifecycle.test.mjs electron/runtime.test.mjs
npm test
```

Expected: all Electron/Node and Vitest tests pass.

### Task 3: Rebuild and verify the Windows release

**Files:**
- Modify: `codex/AI模型任务队列.md`
- Generated/ignored: `a3-front/a3-front/release/`

- [ ] **Step 1: Build the desktop renderer and unpacked package**

Run:

```powershell
npm run build:desktop
npm run desktop:pack
```

Expected: both commands exit 0 and `release/win-unpacked/智学协作台.exe` exists.

- [ ] **Step 2: Verify packaged lifecycle**

Launch the unpacked executable with isolated `A3_ELECTRON_USER_DATA_DIR` and `A3_ELECTRON_TEST_MODE=1`. Require exit code 0, log markers `tray ready`, `backend ready`, `backend stop requested`, `test-mode forcing process exit`, and zero residual processes under `release/win-unpacked`.

- [ ] **Step 3: Build the updated installer**

Run:

```powershell
npm run desktop:dist
```

Expected: NSIS installer and blockmap are regenerated with the tray code and icon.

- [ ] **Step 4: Record exact evidence and commit**

Update S-029 to `完成`, record test counts, package hashes, icon validation and lifecycle result, then run:

```powershell
git diff --check
git add a3-front/a3-front/electron a3-front/a3-front/package.json codex/AI模型任务队列.md
git commit -m "fix: add reliable Windows tray exit"
```

## Self-Review

- Spec coverage: tray creation, restore, close-to-tray, full quit, fallback quit, single-instance restore and resource cleanup are assigned to Tasks 1–3.
- Type consistency: `createTrayController`, `mainWindowCloseAction`, `trayController` and `requestQuit` use the same names throughout.
- Scope: no renderer IPC, startup setting or unrelated desktop behavior is added.
