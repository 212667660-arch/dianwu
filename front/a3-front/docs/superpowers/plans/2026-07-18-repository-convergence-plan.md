# Repository Convergence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the completed S-039 branch, task queue, directory layout, and GitHub remote describe the same authoritative project state.

**Architecture:** Keep `codex/s022-s026-remediation` as the functional baseline because it contains the 67 post-remediation commits and final release acceptance. Audit the stale `codex/s022-five-resource-bundle` branch at file level, transplant only non-regressive repository hygiene changes, then verify and push the latest branch without deleting or force-updating existing branches.

**Tech Stack:** Git worktrees, PowerShell, Python/pytest, Node.js, Electron, Vue/Vitest.

---

### Task 1: Establish The Authoritative Baseline

**Files:**
- Modify: `codex/AI模型任务队列.md`
- Create: `front/a3-front/docs/superpowers/plans/2026-07-18-repository-convergence-plan.md`

- [x] **Step 1: Register S-040 as the only in-progress Sol task**

Set the current batch to S-040 and add the task after S-039 with dependencies on S-039, the stale sync branch, and `origin/main`.

- [x] **Step 2: Confirm worktree isolation and branch relationship**

Run:

```powershell
git rev-parse --git-dir
git rev-parse --git-common-dir
git branch --show-current
git rev-list --left-right --count codex/s022-five-resource-bundle...codex/s022-s026-remediation
```

Expected: linked worktree on `codex/s022-s026-remediation`, with the stale and latest branches diverged from `fb7bcfe`.

- [x] **Step 3: Record a clean functional baseline**

Run the existing latest-branch test entrypoints before transplanting stale-branch changes. Generated `.tmp` and `dist-s033*` directories remain untracked and must not be staged.

### Task 2: Audit And Select Stale-Branch Changes

**Files:**
- Compare: commit `9806f78`
- Compare: `backend/protocols/v2/models.py`
- Compare: `backend/services/resource_bundle/planner.py`
- Compare: `backend/services/resource_bundle/pipeline.py`
- Compare: `.gitignore`, `README.md`, `backend/quick_test.ps1`, `backend/tests/test_model_preferences.py`

- [x] **Step 1: Reject production-code rollback**

Confirm the latest models, planner, pipeline, content safety, OCR, knowledge, and Electron files contain post-S-039 behavior. Do not cherry-pick or merge `9806f78` wholesale.

- [x] **Step 2: Select repository-hygiene changes**

Keep only:

```text
outer frontend directory: a3-front/ -> front/
.gitignore: **/desktop-backend.backup-*/
README and frontend README current paths
quick_test.ps1: prefer project .venv, then backend/competition
portable quick-test entrypoint regression
model preference test reset for repeated persistent-database runs
the two missing S-022 reference documents
the user-authored INBOX-009 completion record
origin/main README title change
```

### Task 3: Apply Directory, Documentation, And Test Corrections

**Files:**
- Rename: `a3-front/` to `front/`
- Modify: `.gitignore`
- Modify: `README.md`
- Modify: `front/a3-front/README.md`
- Modify: `backend/quick_test.ps1`
- Create: `backend/tests/test_quick_test_entrypoint.py`
- Modify: `backend/tests/test_model_preferences.py`
- Create: `front/a3-front/docs/superpowers/plans/2026-07-16-five-resource-bundle-implementation.md`
- Create: `front/a3-front/docs/superpowers/specs/2026-07-16-deepseek-write.md`
- Modify: `codex/AI模型任务队列.md`

- [x] **Step 1: Rename the complete latest frontend tree**

Run `git mv a3-front front` from the latest worktree so all S-039 files move together and Git can detect renames.

- [x] **Step 2: Apply portable test and documentation changes**

Use the latest branch implementations as the base. The quick-test regression must pass when `.venv` exists and must not fail in a fresh clone where `.venv` is absent.

- [x] **Step 3: Repair queue structure**

Move S-024 and S-025 into the Sol task table, add INBOX-009 and S-040, replace the obsolete implementation audit with current facts, and keep historical completion records intact.

### Task 4: Verify The Converged Tree

**Files:**
- Verify: `backend/`
- Verify: `front/a3-front/`

- [x] **Step 1: Run backend verification**

Run:

```powershell
& .\.test-venv\Scripts\python.exe -m compileall -q backend
& .\.test-venv\Scripts\python.exe -m pytest -q backend
```

Expected: no failures; the accepted S-039 baseline was 559 passed and 7 skipped.

- [x] **Step 2: Run Electron and frontend verification**

Run from `front/a3-front`:

```powershell
npm test
npm run build:desktop
```

Expected: no failures; the accepted S-039 baseline was Electron/Node 180 passed and Vitest 151 passed.

- [x] **Step 3: Run repository safety checks**

Run `git diff --check`, high-confidence secret scanning, ignored generated-output checks, and rename-aware staged diff review.

### Task 5: Finalize Queue And Push The Latest Branch

**Files:**
- Modify: `codex/AI模型任务队列.md`

- [ ] **Step 1: Commit the verified implementation**

Commit the reviewed directory, documentation, queue, and test corrections so the working tree is clean before integration.

- [ ] **Step 2: Integrate `origin/main` without rewriting history**

Merge `origin/main` into `codex/s022-s026-remediation`, preserve the remote README title change, and resolve only genuine path conflicts.

- [ ] **Step 3: Push and verify implementation remote identity**

Push `codex/s022-s026-remediation` to `https://github.com/212667660-arch/dianwu.git` without force and without deleting the stale branch. Confirm local HEAD, upstream HEAD, and `git ls-remote` hashes are identical and ahead/behind is `0 0`.

- [ ] **Step 4: Mark S-040 complete with exact evidence**

Record modified files, exact test counts, build result, implementation and merge commit hashes, branch name, remote URL, remote verification, and known non-blocking signing limitation. Set the current batch to no ready tasks, commit and push the completion record, then verify final remote identity again.
