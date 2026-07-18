# Offline OCR and Page Citations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship an offline Chinese OCR pipeline with page checkpoints, failed-page retry, progress/ETA, formula-safe text, and exact PDF page citations.

**Architecture:** Add a lazy RapidOCR adapter behind the existing OCR protocol, extend worker/import job events for page state, and preserve successful page blocks across retries. Keep renderer access behind current Electron knowledge IPC.

**Tech Stack:** Python, FastAPI, SQLAlchemy, PyMuPDF, RapidOCR/ONNX Runtime, PyInstaller, Electron, Vue 3, Vitest.

---

### Task 1: OCR engine adapter and formula normalization

**Files:** Create `backend/knowledge/ocr_engine.py`; modify `backend/requirements.txt`; test `backend/tests/knowledge/test_ocr_engine.py`.

- [ ] Write tests proving ordered Chinese lines, math symbols, empty results, lazy initialization and close behavior.
- [ ] Run `python -m pytest -q backend/tests/knowledge/test_ocr_engine.py` and confirm missing-module failures.
- [ ] Implement `RapidOcrEngine.recognize()` and `normalize_math_text()` with no network access.
- [ ] Re-run the focused tests and commit.

### Task 2: Page checkpoints, failures and retry selection

**Files:** Modify `backend/knowledge/ocr.py`, `backend/knowledge/worker_protocol.py`, `backend/knowledge/models.py`, `backend/knowledge/repository.py`; test `backend/tests/knowledge/test_ocr.py`, `test_worker_protocol.py`, `test_repository.py`.

- [ ] Add failing tests for `pages_done`, `failed_pages`, `current_page`, `page_count`, `eta_seconds` and retrying only `{2,5}`.
- [ ] Verify RED with the focused pytest command.
- [ ] Add bounded per-page timeout, continue-on-page-failure, page selection and persisted JSON failure state.
- [ ] Verify GREEN and commit.

### Task 3: Worker and import-service OCR orchestration

**Files:** Modify `backend/knowledge/worker_main.py`, `backend/knowledge/import_service.py`, `backend/knowledge/optional_packs.py`, `backend/knowledge/service.py`; test `backend/tests/knowledge/test_import_service.py`, `test_packaged_worker.py`, `test_optional_packs.py`.

- [ ] Add failing tests for automatic OCR when available, safe `OCR_REQUIRED` when absent, partial-page persistence, retry and atomic index replacement.
- [ ] Run focused tests and confirm expected failures.
- [ ] Implement OCR capability injection into isolated/frozen workers and staging-block reuse.
- [ ] Run focused tests, then `python -m pytest -q backend/tests/knowledge`, and commit.

### Task 4: API, renderer progress and page navigation

**Files:** Modify `backend/knowledge/schemas.py`, `backend/routers/knowledge.py`, `a3-front/a3-front/src/api/types.ts`, `src/components/knowledge/DocumentGrid.vue`, `DocumentInspector.vue`, related tests, and Electron IPC tests.

- [ ] Add failing API/Vue tests for page `3/188`, ETA, failed-page reason, retry OCR and citation page navigation.
- [ ] Verify RED in pytest and Vitest.
- [ ] Implement the response fields, retry action and accessible UI labels.
- [ ] Verify focused backend/Node/Vitest tests and commit.

### Task 5: Packaging and real OCR acceptance

**Files:** Modify `backend/build_api.ps1`, PyInstaller spec/hooks as needed, `README.md`, queue evidence.

- [ ] Add a packaged-worker test that imports the OCR adapter without source-tree dependencies.
- [ ] Build `api.exe`, run OCR on a generated scanned Chinese/math fixture, and verify page locators.
- [ ] Record real scanned-PDF results or an explicit external-file limitation in S-033 evidence.
