# Release Acceptance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove the backend, web renderer, Electron runtime and packaged desktop application run correctly after S-033 through S-036.

**Architecture:** Use isolated data directories, automated suites, packaged-worker checks and a deterministic desktop smoke harness; record exact evidence in the queue.

**Tech Stack:** pytest, Node test, Vitest, Vite, PyInstaller, electron-builder, PowerShell process checks.

---

### Task 1: Full source verification

- [ ] Run compileall and full backend pytest in a fresh `A3_DATA_DIR`.
- [ ] Run Electron Node tests, Vitest and `npm run build:desktop`.
- [ ] Fix every regression with a failing test first and re-run full suites.

### Task 2: Backend and desktop packaging

- [ ] Build/verify PyInstaller backend and copy it into `desktop-backend`.
- [ ] Run `npm run desktop:pack` and `npm run desktop:dist`.
- [ ] Verify expected executables/installers, versions and OCR runtime files.

### Task 3: Packaged lifecycle smoke

- [ ] Launch with isolated user data and verify ready health, onboarding, demo and knowledge routes.
- [ ] Exercise tray hide/show, pet show/settings and complete exit.
- [ ] Confirm no Electron/api/worker descendants remain and export a redacted diagnostic report.

### Task 4: Queue and delivery evidence

- [ ] Update S-033 through S-037 statuses, changed files, commands, counts, artifact paths and limitations.
- [ ] Review git diff and run final verification commands again before any completion claim.
