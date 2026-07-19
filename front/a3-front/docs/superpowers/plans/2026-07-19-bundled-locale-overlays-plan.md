# Bundled Locale Overlays Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a simple built-in zh-CN/en-US/zh-TW language switcher with persistence and Chinese fallback.

**Architecture:** Keep zh-CN as the complete catalog and merge small built-in en-US/zh-TW overlays at startup. Persist only an allowlisted locale string in localStorage and expose switching through the existing language settings card.

**Tech Stack:** Vue 3, vue-i18n, TypeScript, Vitest, localStorage.

---

### Task 1: Runtime registration and persistence

**Files:**
- Create: `src/i18n/bundled-locales.ts`
- Modify: `src/i18n/index.ts`
- Test: `src/i18n/runtime.test.ts`

- [ ] Add failing tests for bundled locale availability, persisted activation, invalid-value fallback, and missing-key Chinese fallback.
- [ ] Run `npx vitest run src/i18n/runtime.test.ts` and confirm the new tests fail because bundled locales are not registered.
- [ ] Add the two safe overlay dictionaries and allowlisted localStorage helpers.
- [ ] Re-run the focused test and confirm it passes.

### Task 2: Settings-page switching

**Files:**
- Modify: `src/views/DesktopSettings.vue`
- Modify: `src/components/language/LanguageSettingsCard.vue`
- Test: `src/views/DesktopSettings.test.ts`
- Test: `src/components/language/LanguageSettingsCard.test.ts`

- [ ] Add failing tests proving all three bundled languages appear and activation changes the runtime locale.
- [ ] Run the two focused test files and confirm failure because only zh-CN is supplied.
- [ ] Supply three built-in summaries and handle the fixed `activate` event with the runtime persistence helper.
- [ ] Re-run the focused tests and confirm they pass.

### Task 3: Queue, verification, and delivery

**Files:**
- Modify: `codex/AI模型任务队列.md`
- Modify: `codex/当前对话任务锚点.md`

- [ ] Run `npm test`, `npx vue-tsc -b`, `npm run build:desktop`, and `git diff --check`.
- [ ] Record the exact scope and explicitly retain the formal downloadable-pack tasks.
- [ ] Commit and push `codex/s041-signing-i18n-design`.
