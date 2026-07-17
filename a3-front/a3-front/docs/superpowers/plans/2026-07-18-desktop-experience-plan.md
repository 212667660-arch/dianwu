# Desktop Experience Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add first-run guidance, complete tray controls, diagnostics/log export, version/update status and robust pet settings.

**Architecture:** Keep privileged desktop state, diagnostics and file dialogs in the main process; expose minimal typed preload APIs; render configuration in existing Vue settings surfaces.

**Tech Stack:** Electron, Node test runner, Vue 3, Vitest, electron-builder.

---

### Task 1: Versioned desktop state and onboarding

**Files:** Create `electron/desktop-state.mjs`; modify `main.mjs`, `preload.cjs`, router/views; add Node and Vitest tests.

- [ ] Test first-run detection, atomic state write, corrupt-state recovery and skip-to-offline-demo.
- [ ] Implement minimal state controller and onboarding screen; verify and commit.

### Task 2: Tray and AI pause lifecycle

**Files:** Modify `tray-lifecycle.mjs`, `main.mjs`, backend proxy/controller, tests.

- [ ] Test show main, show pet, pause/resume AI and full exit labels/actions.
- [ ] Implement stateful menu rebuild and request rejection while paused; verify and commit.

### Task 3: Diagnostics, logs, version and update status

**Files:** Create `electron/desktop-diagnostics.mjs`; modify preload/main/settings views; tests.

- [ ] Test redaction of tokens, keys, request text and paths plus safe export and offline update status.
- [ ] Implement diagnostics report, save dialog, version payload and explicit update check result; verify and commit.

### Task 4: Pet management and low-power behavior

**Files:** Modify `pet-config.mjs`, `pet-controller.mjs`, pet renderer/settings components and tests.

- [ ] Test preview, mute/volume, always-on-top, display clamping, state actions and idle frame throttling.
- [ ] Implement settings and controller behavior; run Node/Vitest/build and commit.
