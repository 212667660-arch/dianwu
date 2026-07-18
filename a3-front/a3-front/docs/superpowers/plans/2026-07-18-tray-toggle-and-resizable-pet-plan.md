# Tray Toggle and Resizable Pet Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make tray items toggle the main window and Motuan predictably, and support persistent proportional corner resizing without click-driven size changes.

**Architecture:** Keep visibility decisions in small main-process controllers. Add a validated resize gesture to the existing pet controller and expose only fixed resize IPC methods through the sandbox preload. The renderer detects four corner hit zones while the main process remains authoritative for bounds and persistence.

**Tech Stack:** Electron 32, Node test runner, sandbox preload IPC, vanilla browser pointer events, JSON settings persistence.

---

### Task 1: Dedicated test environment and queue

**Files:**
- Modify: `.gitignore`
- Modify: `codex/AI模型任务队列.md`

- [ ] Add `**/.test-venv/` to the Python environment ignore section.
- [ ] Expand S-039 acceptance to include tray toggle behavior, persistent proportional pet resizing, and the dedicated test environment.
- [ ] Create `.test-venv` with uv and install `backend/requirements.txt` without running tests.

### Task 2: Window toggle behavior

**Files:**
- Modify: `electron/tray-lifecycle.mjs`
- Modify: `electron/tray-lifecycle.test.mjs`
- Modify: `electron/main.mjs`
- Modify: `electron/pet-controller.mjs`
- Modify: `electron/pet-controller.test.mjs`

- [ ] Add tests for focused main-window minimization and hidden/background restoration.
- [ ] Split explicit `showMainWindow()` from `toggleMainWindow()` so second-instance startup never minimizes an existing window.
- [ ] Add `toggleVisibility()` to the pet controller: visible pets hide; hidden pets show inactive and move to the top.
- [ ] Wire both tray menu items to the toggle methods and keep tray single/double click on the main-window toggle.

### Task 3: Persistent proportional pet resizing

**Files:**
- Modify: `electron/pet-controller.mjs`
- Modify: `electron/pet-controller.test.mjs`
- Modify: `electron/pet-preload.cjs`
- Modify: `electron/main.mjs`
- Modify: `electron/runtime.test.mjs`
- Modify: `electron/pet/pet-renderer.js`
- Modify: `electron/pet-renderer.test.mjs`
- Modify: `electron/pet/pet.css`

- [ ] Add pure corner detection and proportional resize calculations with 1× minimum and 3× maximum dimensions.
- [ ] Add validated `beginResize`, `moveResize`, and `endResize` controller methods that clamp to display work areas and persist final bounds.
- [ ] Restore saved width and height on startup; a settings scale update still resets to the selected preset.
- [ ] Expose only three fixed resize bridge methods and register sender-checked IPC listeners.
- [ ] Route corner pointer gestures to resize and all other pointer gestures to position dragging/click animation.
- [ ] Add visible cursor feedback for four resize corners while preserving the transparent canvas.

### Task 4: Resolve earlier review races

**Files:**
- Modify: `src/views/KnowledgeLibrary.vue`
- Modify: `src/views/KnowledgeLibrary.test.ts`
- Modify: `electron/pet/pet-renderer.js`
- Modify: `electron/pet-renderer.test.mjs`

- [ ] Serialize or reconcile favorite updates so refresh overlap cannot replace a successful local result or roll back unrelated document fields.
- [ ] Cancel a pending delayed single click when any interaction animation starts, and prevent delayed callbacks from extending an active animation.

### Task 5: Verification after implementation

**Files:**
- Modify: `codex/AI模型任务队列.md`

- [ ] Run Electron tray/pet and knowledge favorite tests.
- [ ] Run `npm test` and `npm run build:desktop`.
- [ ] Run backend pytest using `.test-venv\\Scripts\\python.exe` and an isolated `A3_DATA_DIR`.
- [ ] Run `npm run desktop:pack`, `npm run desktop:dist`, unpacked lifecycle verification, and record hashes.
- [ ] Request final code review; fix all Critical and Important findings before marking S-039 complete.

