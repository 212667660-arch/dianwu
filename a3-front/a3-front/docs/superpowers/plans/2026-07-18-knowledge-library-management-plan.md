# Knowledge Library Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add multi-collection documents, bulk operations, recycle bin, tags, favorites, filters, sort and duplicate explanations.

**Architecture:** Extend the normalized knowledge schema, keep one document/object per SHA-256, expose bounded bulk commands, and add a selection-oriented Vue workspace.

**Tech Stack:** SQLAlchemy/SQLite, FastAPI/Pydantic, Electron IPC allowlists, Vue 3/Pinia/Vitest.

---

### Task 1: Schema migration and repository behavior

**Files:** Modify `backend/knowledge/models.py`, `repository.py`, database initialization; test `backend/tests/knowledge/test_repository.py`.

- [ ] Write failing tests for many collections, tags, favorite, soft delete, restore and 30-day purge eligibility.
- [ ] Verify RED, implement additive SQLite migration and repository methods, verify GREEN, commit.

### Task 2: Bulk and duplicate APIs

**Files:** Modify `backend/knowledge/schemas.py`, `service.py`, `routers/knowledge.py`; test `test_knowledge_api.py`, `test_import_service.py`.

- [ ] Add failing tests for bounded bulk actions, partial results, search exclusion and duplicate explanations.
- [ ] Implement fixed action schemas and service transactions; run focused and knowledge suites; commit.

### Task 3: Electron transport contract

**Files:** Modify `electron/ipc-contract.mjs`, `backend-proxy.mjs`, tests.

- [ ] Add failing route/body validation tests for list filters, bulk actions and restore/purge.
- [ ] Extend only fixed knowledge routes and byte/ID limits; run Node tests; commit.

### Task 4: Selection, recycle bin, tags and filters UI

**Files:** Modify `src/views/KnowledgeLibrary.vue`, `src/components/knowledge/DocumentGrid.vue`, `DocumentInspector.vue`, API/store types; create focused components if a file exceeds one responsibility; test related Vitest files.

- [ ] Add failing tests for select all, bulk move/delete, restore, favorite, tags, sort, advanced filters, progress detail and duplicate prompt.
- [ ] Implement accessible controls and refresh semantics; run Vitest and desktop build; commit.
