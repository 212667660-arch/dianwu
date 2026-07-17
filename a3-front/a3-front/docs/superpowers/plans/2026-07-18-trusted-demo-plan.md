# Trusted Learning and Competition Demo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add page-range grounded learning, answer review, evidence recovery actions and a truthful offline one-click demo.

**Architecture:** Extend retrieval contracts, add a deterministic/reviewer validation layer, seed isolated demo data, and visualize existing agent events without exposing prompts.

**Tech Stack:** FastAPI, existing LLM gateway and resource pipeline, SQLite, Vue 3, Electron.

---

### Task 1: Page-range retrieval and evidence actions

**Files:** Modify knowledge search/context schemas, chat/resource request schemas and tests.

- [ ] Test inclusive page filtering, empty evidence, retry and expanded range.
- [ ] Implement bounded fields and structured evidence status; verify and commit.

### Task 2: Textbook/model sections and answer reviewer

**Files:** Modify resource specialists/orchestrator/protocols; add reviewer service and tests.

- [ ] Test section separation, citation ownership, formula/substitution checks and one repair attempt.
- [ ] Implement reviewer verdicts and safe warning fallback; verify and commit.

### Task 3: Demo dataset and orchestration

**Files:** Create `backend/demo/` seed/service/routes and fixtures; modify database/service tests.

- [ ] Test idempotent isolated seed, no copyrighted full text, offline status and reset.
- [ ] Implement demo workspace API and data; verify and commit.

### Task 4: One-click demo and agent visualization

**Files:** Modify Dashboard, AgentWorkspace, SmartTutor, mastery chart and routes; tests.

- [ ] Test one-click navigation, truthful offline badge, agent steps, before/after mastery and degradation message.
- [ ] Implement the guided flow; run Vitest/build and commit.
