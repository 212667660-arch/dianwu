# Unified Error Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every A3 HTTP non-2xx response use the safe `code/message/retryable/request_id` contract and convert it into one consistent Web/Electron client error type.

**Architecture:** FastAPI owns one error response builder and converts domain errors, resource misses, automatic validation failures, framework HTTP failures and unexpected failures into the fixed envelope. Web transport parses only that envelope into `BackendApiError`; Electron continues to proxy the same envelope without exposing upstream diagnostics. Existing `DesktopApiError` remains a compatibility export.

**Tech Stack:** FastAPI, Starlette, Pydantic v2, pytest, Vue 3, TypeScript, Axios, Vitest, Electron, Node `node:test`.

---

## File map

- `backend/errors.py`: safe resource, readiness and request-validation `AppError` constructors.
- `backend/main.py`: one JSON response helper plus FastAPI/Starlette/validation/unexpected exception handlers.
- `backend/routers/chat.py`, `backend/routers/sessions.py`, `backend/routers/learning.py`: replace expected `HTTPException` paths with typed business errors.
- `backend/tests/test_errors_and_sessions.py`, `backend/tests/test_api.py`, `backend/tests/test_learning_progress.py`, `backend/tests/test_export_and_evaluation_cli.py`: assert the fixed envelope for 404, 422, 503 and 500 paths.
- `src/api/transport.ts`: common `BackendApiError`, envelope validation and compatibility export.
- `src/api/web-transport.ts`: parse Web normal and SSE setup failures into the common error type.
- `src/api/web-transport.test.ts`: Web request/SSE/error-message regression coverage.
- `src/api/desktop-transport.test.ts`, `electron/backend-proxy.test.mjs`: prove desktop fields match the same contract and malformed upstream data remains safe.
- `codex/AI模型任务队列.md`: T-029 result and final verification evidence.

## Execution context

Implementation runs on branch `terra/t029-error-contract` in the isolated worktree `E:\软件杯\.worktrees\t029-error-contract`. The repository-root `.gitignore` must ignore `.worktrees/` before the worktree is created; generated build outputs remain ignored by the existing root and nested rules.

### Task 0: Prepare the isolated implementation branch

**Files:**
- Modify: `.gitignore`
- Create: `E:\软件杯\.worktrees\t029-error-contract` (Git worktree)

- [ ] **Step 1: Add the worktree directory to the root ignore rules**

Add this exact entry under the local verification section of `.gitignore`:

```gitignore
.worktrees/
```

- [ ] **Step 2: Commit the plan and isolation rule on `main`**

Run:

```powershell
cd E:\软件杯
git add .gitignore a3-front/a3-front/docs/superpowers/plans/2026-07-15-unified-error-contract-plan.md
git commit -m "docs: plan unified error contract"
```

Expected: the plan and ignore rule are committed before branch creation.

- [ ] **Step 3: Create and verify the worktree**

Run:

```powershell
git worktree add .worktrees/t029-error-contract -b terra/t029-error-contract
git -C .worktrees/t029-error-contract status --short
git -C .worktrees/t029-error-contract branch --show-current
```

Expected: the worktree is clean and reports `terra/t029-error-contract`.

### Task 1: Establish the backend envelope and framework exception mapping

**Files:**
- Modify: `backend/errors.py`
- Modify: `backend/main.py`
- Modify: `backend/tests/test_errors_and_sessions.py`
- Modify: `backend/tests/test_api.py`

- [ ] **Step 1: Write failing error-handler tests**

Add a shared assertion helper and these tests before changing application code:

```python
def assert_error(response, status: int, code: str, retryable: bool = False) -> None:
    assert response.status_code == status
    body = response.json()
    assert body["code"] == code
    assert body["retryable"] is retryable
    assert isinstance(body["message"], str) and body["message"]
    assert isinstance(body["request_id"], str) and body["request_id"]
    assert response.headers["X-Request-ID"] == body["request_id"]
    assert "detail" not in body


def test_request_validation_uses_safe_envelope() -> None:
    with TestClient(app) as client:
        response = client.post("/api/chat", json={"message": "", "session_id": "bad/id"})
    assert_error(response, 422, "REQUEST_VALIDATION_ERROR")


def test_not_ready_health_uses_safe_envelope(monkeypatch) -> None:
    from backend.config import Settings
    monkeypatch.setattr(
        "backend.main.get_settings",
        lambda: Settings(model_api_key="", openai_api_key="", hy_api_key=""),
    )
    with TestClient(app) as client:
        response = client.get("/health/ready", headers={"X-Request-ID": "trace-ready"})
    assert_error(response, 503, "MODEL_NOT_READY")
    assert response.json()["request_id"] == "trace-ready"


def test_unexpected_failure_does_not_expose_exception_text(monkeypatch) -> None:
    async def fail(*_args, **_kwargs):
        raise RuntimeError("private database path and token")
    monkeypatch.setattr(chat, "handle_message", fail)
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post("/api/chat", json={"message": "测试", "session_id": "error_case"})
    assert_error(response, 500, "BACKEND_UNEXPECTED_ERROR", retryable=True)
    assert "private database" not in response.text


def test_unknown_route_and_method_use_safe_framework_envelopes() -> None:
    with TestClient(app) as client:
        missing = client.get("/api/does-not-exist")
        method = client.put("/health/live")
    assert_error(missing, 404, "HTTP_NOT_FOUND")
    assert_error(method, 405, "HTTP_METHOD_NOT_ALLOWED")
```

- [ ] **Step 2: Run the focused backend tests and confirm RED**

Run:

```powershell
cd E:\软件杯\backend
.\competition\Scripts\python.exe -m pytest -q tests/test_errors_and_sessions.py tests/test_api.py
```

Expected: at least the validation and readiness assertions fail because FastAPI currently returns `detail` or `{ status, reason }`.

- [ ] **Step 3: Add typed errors and one response builder**

In `backend/errors.py`, add the following safe constructors while retaining existing `AppError` subclasses:

```python
class ResourceNotFoundError(AppError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(code, message, 404)


class RequestValidationAppError(AppError):
    def __init__(self) -> None:
        super().__init__("REQUEST_VALIDATION_ERROR", "请求参数无效。", 422)


class ModelNotReadyError(AppError):
    def __init__(self) -> None:
        super().__init__("MODEL_NOT_READY", "模型服务尚未配置。", 503)


class HttpNotFoundError(AppError):
    def __init__(self) -> None:
        super().__init__("HTTP_NOT_FOUND", "请求的接口不存在。", 404)


class HttpMethodNotAllowedError(AppError):
    def __init__(self) -> None:
        super().__init__("HTTP_METHOD_NOT_ALLOWED", "当前请求方法不受支持。", 405)
```

In `backend/main.py`, import `RequestValidationError` and Starlette's `HTTPException`, then make every error path call one helper:

```python
def error_response(request: Request, error: AppError, *, headers: dict[str, str] | None = None) -> JSONResponse:
    request_id = request.headers.get("X-Request-ID") or uuid4().hex
    response_headers = {"X-Request-ID": request_id, **(headers or {})}
    return JSONResponse(
        status_code=error.http_status,
        content={
            "code": error.code,
            "message": error.public_message,
            "retryable": error.retryable,
            "request_id": request_id,
        },
        headers=response_headers,
    )
```

Add handlers in this order:

```python
@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    log_error(request, exc)
    return error_response(request, exc)


@app.exception_handler(RequestValidationError)
async def request_validation_handler(request: Request, _exc: RequestValidationError) -> JSONResponse:
    return error_response(request, RequestValidationAppError())


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    error = HttpNotFoundError() if exc.status_code == 404 else HttpMethodNotAllowedError() if exc.status_code == 405 else AppError("HTTP_REQUEST_ERROR", "请求无法处理。", exc.status_code)
    return error_response(request, error)


@app.exception_handler(Exception)
async def unexpected_exception_handler(request: Request, _exc: Exception) -> JSONResponse:
    return error_response(request, UnexpectedBackendError())
```

Replace the authentication and rate-limit `JSONResponse(...)` calls in `DesktopAuthMiddleware` with `error_response(...)`, retaining `Retry-After` for rate limiting. Replace the `ready()` 503 response with `raise ModelNotReadyError()`.

- [ ] **Step 4: Run the focused backend tests and confirm GREEN**

Run the command from Step 2.

Expected: all focused tests pass; every tested 422, 503 and 500 response has exactly the stable public fields and an `X-Request-ID` header.

- [ ] **Step 5: Commit the backend framework mapping**

```powershell
git add backend/errors.py backend/main.py backend/tests/test_errors_and_sessions.py backend/tests/test_api.py
git commit -m "feat: standardize backend error envelopes"
```

### Task 2: Convert route-level 404 and 422 paths to business codes

**Files:**
- Modify: `backend/routers/chat.py`
- Modify: `backend/routers/sessions.py`
- Modify: `backend/routers/learning.py`
- Modify: `backend/tests/test_errors_and_sessions.py`
- Modify: `backend/tests/test_learning_progress.py`
- Modify: `backend/tests/test_export_and_evaluation_cli.py`

- [ ] **Step 1: Write failing route-code tests**

Add assertions that distinguish expected resource failures:

```python
def test_missing_session_uses_session_not_found_code() -> None:
    with TestClient(app) as client:
        response = client.get("/api/sessions/no_such_session")
    assert_error(response, 404, "SESSION_NOT_FOUND")


def test_unknown_generation_uses_generation_not_found_code(monkeypatch) -> None:
    monkeypatch.setattr(chat, "cancel_generation", lambda *_args: False)
    with TestClient(app) as client:
        response = client.delete("/api/generations/missing?session_id=student_01")
    assert_error(response, 404, "GENERATION_NOT_FOUND")
```

Update the existing missing-question and missing-resource tests to assert `QUESTION_NOT_FOUND` and `LEARNING_RESOURCE_NOT_FOUND`; preserve the existing status-code assertions.

- [ ] **Step 2: Run the route tests and confirm RED**

Run:

```powershell
cd E:\软件杯\backend
.\competition\Scripts\python.exe -m pytest -q tests/test_errors_and_sessions.py tests/test_learning_progress.py tests/test_export_and_evaluation_cli.py
```

Expected: code assertions fail because these routes still emit FastAPI `detail` responses.

- [ ] **Step 3: Replace `HTTPException` with typed `ResourceNotFoundError`**

Remove `HTTPException` imports from the three routers and replace each expected resource miss:

```python
raise ResourceNotFoundError("SESSION_NOT_FOUND", "会话不存在。")
raise ResourceNotFoundError("GENERATION_NOT_FOUND", "生成任务不存在、已结束或不属于该会话。")
raise ResourceNotFoundError("LEARNING_RESOURCE_NOT_FOUND", "学习资源不存在。")
raise ResourceNotFoundError("QUESTION_NOT_FOUND", "练习题不存在或不属于该会话。")
```

Remove the unreachable manual `format not in {"markdown", "txt"}` check from `sessions.py`; the existing `Literal["markdown", "txt"]` annotation is handled by the application-level `RequestValidationError` handler.

- [ ] **Step 4: Run the route tests and confirm GREEN**

Run the command from Step 2.

Expected: route-specific 404 codes are stable and invalid query input uses `REQUEST_VALIDATION_ERROR` without `detail`.

- [ ] **Step 5: Commit the route mappings**

```powershell
git add backend/routers/chat.py backend/routers/sessions.py backend/routers/learning.py backend/tests/test_errors_and_sessions.py backend/tests/test_learning_progress.py backend/tests/test_export_and_evaluation_cli.py
git commit -m "feat: expose stable resource error codes"
```

### Task 3: Unify the Web client error object and parsing

**Files:**
- Modify: `a3-front/a3-front/src/api/transport.ts`
- Modify: `a3-front/a3-front/src/api/web-transport.ts`
- Create: `a3-front/a3-front/src/api/web-transport.test.ts`
- Modify: `a3-front/a3-front/src/api/desktop-transport.test.ts`

- [ ] **Step 1: Write failing Web transport tests**

Create `web-transport.test.ts` around exported pure helpers and mocked `fetch`:

```ts
it('converts a canonical Web 404 envelope to BackendApiError', () => {
  const error = backendApiErrorFromEnvelope(404, {
    code: 'SESSION_NOT_FOUND', message: '会话不存在。', retryable: false, request_id: 'req-web-404',
  })
  expect(error).toMatchObject({
    name: 'BackendApiError', status: 404, code: 'SESSION_NOT_FOUND', retryable: false, requestId: 'req-web-404',
  })
})

it('uses a safe generic error for a malformed non-2xx response', () => {
  const error = backendApiErrorFromEnvelope(502, { detail: 'private upstream details' })
  expect(error).toMatchObject({ code: 'BACKEND_HTTP_ERROR', retryable: true })
  expect(error.message).not.toContain('private upstream')
})
```

Add a desktop test that imports `BackendApiError` and confirms a desktop envelope is also an instance of it.

- [ ] **Step 2: Run the focused Vitest files and confirm RED**

Run:

```powershell
cd E:\软件杯\a3-front\a3-front
npx vitest run src/api/web-transport.test.ts src/api/desktop-transport.test.ts
```

Expected: FAIL because `BackendApiError` and `backendApiErrorFromEnvelope` do not exist.

- [ ] **Step 3: Add the common type and canonical Web parsing**

In `transport.ts`, add the common class and exported parser:

```ts
export class BackendApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly retryable = false,
    readonly requestId?: string,
  ) {
    super(message)
    this.name = 'BackendApiError'
  }
}

export { BackendApiError as DesktopApiError }

export function backendApiErrorFromEnvelope(status: number, value: unknown): BackendApiError {
  if (isBackendErrorEnvelope(value)) {
    return new BackendApiError(status, value.code, value.message, value.retryable, value.request_id)
  }
  return new BackendApiError(
    status,
    'BACKEND_HTTP_ERROR',
    '服务请求未成功，请稍后重试。',
    status >= 500,
  )
}
```

`isBackendErrorEnvelope` must require an object with non-empty string `code`, non-empty string `message`, boolean `retryable`, and optional string `request_id`.

In `web-transport.ts`, configure Axios with `validateStatus: () => true`. For normal requests, parse any non-2xx `response.data` through `backendApiErrorFromEnvelope`; for Axios network errors return a `BackendApiError(503, "BACKEND_UNAVAILABLE", "服务暂时不可用，请稍后重试。", true)`. For fetch SSE setup failures, pass parsed JSON through the same helper. `errorMessage()` returns `BackendApiError.message` and uses only safe generic fallback text for unknown/Axios network errors; remove all `detail` reads.

- [ ] **Step 4: Run the focused Vitest files and confirm GREEN**

Run the command from Step 2.

Expected: Web ordinary errors, SSE setup errors and desktop envelopes expose the same status/code/message/retryable/requestId fields; malformed bodies do not leak `detail`.

- [ ] **Step 5: Commit the Web contract**

```powershell
git add a3-front/a3-front/src/api/transport.ts a3-front/a3-front/src/api/web-transport.ts a3-front/a3-front/src/api/web-transport.test.ts a3-front/a3-front/src/api/desktop-transport.test.ts
git commit -m "feat: unify Web and desktop API errors"
```

### Task 4: Verify Electron proxy preservation and release-wide regression

**Files:**
- Modify: `a3-front/a3-front/electron/backend-proxy.test.mjs`
- Modify: `a3-front/a3-front/README.md`
- Modify: `a3-front/a3-front/src/api/README.md`
- Modify: `codex/AI模型任务队列.md`

- [ ] **Step 1: Write failing Electron contract tests**

Add a table-driven test in `backend-proxy.test.mjs` using canonical 404, 422 and 503 bodies:

```js
for (const [status, code, retryable] of [
  [404, 'SESSION_NOT_FOUND', false],
  [422, 'REQUEST_VALIDATION_ERROR', false],
  [503, 'MODEL_NOT_READY', false],
]) {
  const result = await proxy.request(event, { method: 'GET', path: '/health/ready' })
  assert.deepEqual(result.error, {
    code,
    message: '安全错误文案。',
    retryable,
    requestId: 'req-contract',
  })
}
```

Keep the existing non-JSON and malformed-response tests unchanged; they are the regression boundary that prevents renderer exposure of upstream details.

- [ ] **Step 2: Run Electron tests and confirm RED or identify an already-green preservation path**

Run:

```powershell
cd E:\软件杯\a3-front\a3-front
node --test electron/backend-proxy.test.mjs
```

Expected: the new table either demonstrates existing correct preservation or identifies a missing `request_id`/retryable conversion; only change `backend-proxy.mjs` if this focused test fails.

- [ ] **Step 3: Make the minimal Electron adjustment when RED**

If focused tests fail because a valid `request_id` or boolean `retryable` is dropped, adjust only `mapBackendFailure` / `streamHttpFailure` to use the existing fixed-envelope validator and return:

```js
desktopError(body.code, body.message, body.retryable, body.request_id)
```

Do not forward unknown JSON fields, response text, headers, token or backend URL.

- [ ] **Step 4: Run full regression and both builds**

Run:

```powershell
cd E:\软件杯\backend
powershell -NoProfile -ExecutionPolicy Bypass -File .\quick_test.ps1

cd E:\软件杯\a3-front\a3-front
npm run test
npm run build
npm run build:desktop
```

Expected: backend tests, Electron Node tests, Vitest, Web build and desktop build all exit with code 0.

- [ ] **Step 5: Update documentation, queue and commit**

Document the public error envelope in both README files. Record exact test counts and the 404/422/503 Web/Electron verification in `codex/AI模型任务队列.md`, then mark T-029 complete.

```powershell
git add a3-front/a3-front/electron/backend-proxy.mjs a3-front/a3-front/electron/backend-proxy.test.mjs a3-front/a3-front/README.md a3-front/a3-front/src/api/README.md codex/AI模型任务队列.md
git commit -m "docs: complete unified error contract"
git push origin terra/t029-error-contract
```

## Plan self-review

- The four tasks map to every approved requirement: fixed envelope, readiness 503, typed resource 404, automatic 422, framework fallback 500, Web parsing, Electron preservation, and full regression.
- All production changes are preceded by a focused failing test and a matching focused verification command.
- Field names remain consistent: backend HTTP uses `request_id`; desktop/frontend uses `requestId`; `BackendApiError` is the shared client type and `DesktopApiError` is its compatibility export.
- The plan intentionally excludes success payloads, SSE normal events, automatic retries, database changes and unrelated UI work.
