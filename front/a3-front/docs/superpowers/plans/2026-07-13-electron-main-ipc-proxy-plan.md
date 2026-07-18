# Electron Main IPC Proxy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the packaged Electron application proxy all FastAPI HTTP/SSE traffic through its main process so the renderer never receives the local backend address or desktop token.

**Architecture:** `electron/ipc-contract.mjs` owns route validation and safe envelopes. `electron/backend-proxy.mjs` owns loopback fetch, token injection, bounded response/SSE parsing, ownership and cancellation. Preload exposes fixed bridge methods only; Vue's `backendApi` uses a desktop transport when that bridge exists and a direct Web transport only for browser development.

**Tech Stack:** Electron 32 IPC, Node fetch and Web Streams, Vue 3, TypeScript, Axios, Vitest, Node `node:test`, Vite, electron-builder.

---

## File structure

| Path | Responsibility |
| --- | --- |
| `electron/ipc-contract.mjs` | Method/path/query/body validation, trusted-sender check, URL assembly and error envelopes. |
| `electron/backend-proxy.mjs` | Token-owning HTTP/SSE proxy, stream registry, bounded body readers and cleanup. |
| `electron/ipc-contract.test.mjs` | Node tests for route validation and sender isolation. |
| `electron/backend-proxy.test.mjs` | Node tests for token injection, HTTP errors, SSE, cancellation and cleanup. |
| `electron/main.mjs` | Backend runtime lifecycle and fixed IPC-handler registration. |
| `electron/preload.mjs` | Narrow `a3Desktop` bridge with request/stream/cancel/subscription methods only. |
| `src/api/transport.ts` | Shared frontend transport types and stable `DesktopApiError`. |
| `src/api/desktop-transport.ts` | Renderer adapter for the fixed Electron bridge. |
| `src/api/web-transport.ts` | Browser-development HTTP/SSE adapter with no Electron runtime values. |
| `src/api/backend.ts` | Existing business API methods refactored to consume `BackendTransport`. |
| `src/env.d.ts` | Type declaration for the minimal `window.a3Desktop` bridge. |

This repository has no `.git` directory. Do not attempt commits; record verification in `codex/AI模型任务队列.md` instead.

### Task 1: Define the allow-listed IPC contract

**Files:**

- Create: `electron/ipc-contract.mjs`
- Create: `electron/ipc-contract.test.mjs`
- Modify: `electron/runtime.mjs`
- Modify: `electron/runtime.test.mjs`
- Modify: `package.json`

- [ ] **Step 1: Write the failing contract tests.**

Create `electron/ipc-contract.test.mjs` before creating the contract module:

```js
import assert from 'node:assert/strict'
import test from 'node:test'

test('accepts only current frontend routes and normalizes safe query values', async () => {
  const { validateDesktopRequest } = await import('./ipc-contract.mjs')
  assert.deepEqual(validateDesktopRequest({
    method: 'GET',
    path: '/api/sessions/student_1/reviews',
    query: { due_only: true },
  }), { ok: true, value: {
    method: 'GET', path: '/api/sessions/student_1/reviews',
    query: { due_only: 'true' }, body: undefined, stream: false,
  } })
})

test('rejects external URLs, traversal, headers, unknown routes and oversize JSON', async () => {
  const { validateDesktopRequest } = await import('./ipc-contract.mjs')
  for (const input of [
    { method: 'GET', path: 'https://example.com/' },
    { method: 'GET', path: '/api/../settings/model' },
    { method: 'GET', path: '/api/unknown' },
    { method: 'GET', path: '/health/live', headers: { Authorization: 'x' } },
    { method: 'POST', path: '/api/chat', body: { message: 'x'.repeat(65_537) } },
  ]) assert.equal(validateDesktopRequest(input).ok, false)
})

test('allows only the exact owner window and renderer entry URL', async () => {
  const { isTrustedDesktopSender } = await import('./ipc-contract.mjs')
  const owner = { id: 7, isDestroyed: () => false }
  assert.equal(isTrustedDesktopSender({ sender: owner, senderFrame: { url: 'file:///app/dist/index.html' } }, owner, 'file:///app/dist/index.html'), true)
  assert.equal(isTrustedDesktopSender({ sender: { id: 7 }, senderFrame: { url: 'file:///app/dist/index.html' } }, owner, 'file:///app/dist/index.html'), false)
  assert.equal(isTrustedDesktopSender({ sender: owner, senderFrame: { url: 'file:///tmp/index.html' } }, owner, 'file:///app/dist/index.html'), false)
})
```

- [ ] **Step 2: Run the test to verify it fails.**

Run: `node --test electron\\ipc-contract.test.mjs`

Expected: `ERR_MODULE_NOT_FOUND` for `electron/ipc-contract.mjs`.

- [ ] **Step 3: Implement the minimal contract.**

Create `electron/ipc-contract.mjs` with `MAX_REQUEST_BYTES = 64 * 1024`, `SESSION_ID = /^[A-Za-z0-9_-]{1,64}$/`, `GENERATION_ID = /^[A-Za-z0-9_-]{1,128}$/`, and exact method/path matchers for:

```text
GET  /health/live | /health/ready | /api/settings/model
POST /api/chat | /api/chat/stream
GET  /api/sessions/:sessionId[/progress|/next-action|/reviews|/mistakes]
POST /api/sessions/:sessionId/rediagnose
POST /api/sessions/:sessionId/questions/:questionId/attempts
DELETE /api/generations/:generationId?session_id=:sessionId
```

Implement this public API:

```js
export function desktopError(code, message, retryable = false, requestId) {
  return { code, message, retryable, ...(requestId ? { requestId } : {}) }
}

export function validateDesktopRequest(input, { stream = false } = {}) {
  // Reject `headers`, `url`, `baseUrl`, `token`, unknown routes, `..`, `\\`, '#',
  // encoded traversal, invalid IDs, non-scalar query values and body JSON > 64 KiB.
  // Return { ok: true, value: { method, path, query, body, stream } }
  // or { ok: false, error: desktopError(...) }.
}

export function isTrustedDesktopSender(event, mainWebContents, indexUrl) {
  return event.sender === mainWebContents
    && !event.sender.isDestroyed()
    && event.senderFrame?.url === indexUrl
}

export function buildBackendUrl(baseUrl, request) {
  const url = new URL(request.path, `${baseUrl}/`)
  for (const [key, value] of Object.entries(request.query || {})) url.searchParams.set(key, value)
  return url.toString()
}
```

Remove `canAccessRuntimeInfo` from `electron/runtime.mjs` and its old test. Update `package.json`:

```json
"test": "node --test electron/runtime.test.mjs electron/backend-lifecycle.test.mjs electron/ipc-contract.test.mjs && vitest run"
```

- [ ] **Step 4: Run the contract and existing Node tests.**

Run: `node --test electron\\runtime.test.mjs electron\\backend-lifecycle.test.mjs electron\\ipc-contract.test.mjs`

Expected: all tests pass.

### Task 2: Proxy normal HTTP requests in the Electron main process

**Files:**

- Create: `electron/backend-proxy.mjs`
- Create: `electron/backend-proxy.test.mjs`
- Modify: `package.json`

- [ ] **Step 1: Write failing normal-request tests.**

Create a fake response helper and tests that import `createBackendProxy` before it exists:

```js
function jsonResponse(status, data) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

test('injects the main-only desktop token and returns a safe response envelope', async () => {
  const calls = []
  const { createBackendProxy } = await import('./backend-proxy.mjs')
  const owner = { id: 1, isDestroyed: () => false, send() {} }
  const proxy = createBackendProxy({
    getRuntime: () => ({ baseUrl: 'http://127.0.0.1:49152', token: 'secret-token', indexUrl: 'file:///app/dist/index.html' }),
    getMainWebContents: () => owner,
    fetchImpl: async (url, init) => { calls.push({ url, init }); return jsonResponse(200, { status: 'ready' }) },
  })
  const result = await proxy.request({ sender: owner, senderFrame: { url: 'file:///app/dist/index.html' } }, { method: 'GET', path: '/health/ready' })
  assert.deepEqual(result, { ok: true, status: 200, data: { status: 'ready' } })
  assert.equal(calls[0].init.headers['X-A3-Desktop-Token'], 'secret-token')
  assert.doesNotMatch(calls[0].url, /secret-token/)
})

test('returns safe errors for denied senders, backend JSON errors and network failures', async () => {
  // Assert DESKTOP_REQUEST_DENIED for another sender, backend code/message for a 401 JSON response,
  // and DESKTOP_BACKEND_UNAVAILABLE without an internal URL for a thrown fetch error.
})

test('stops reading a normal response after five MiB', async () => {
  // Supply a ReadableStream with MAX_RESPONSE_BYTES + 1 bytes and assert DESKTOP_RESPONSE_TOO_LARGE.
})
```

- [ ] **Step 2: Run the test to verify it fails.**

Run: `node --test electron\\backend-proxy.test.mjs`

Expected: `ERR_MODULE_NOT_FOUND` for `electron/backend-proxy.mjs`.

- [ ] **Step 3: Implement the normal request proxy.**

Create `electron/backend-proxy.mjs` with this factory and exact response shape:

```js
export function createBackendProxy({ getRuntime, getMainWebContents, fetchImpl = fetch, log = async () => {} }) {
  async function request(event, input) {
    const runtime = getRuntime()
    const validation = validateDesktopRequest(input)
    if (!runtime || !isTrustedDesktopSender(event, getMainWebContents(), runtime.indexUrl)) {
      return { ok: false, status: 403, error: desktopError('DESKTOP_REQUEST_DENIED', '桌面请求未获授权。') }
    }
    if (!validation.ok) return { ok: false, status: 400, error: validation.error }
    try {
      const response = await fetchImpl(buildBackendUrl(runtime.baseUrl, validation.value), {
        method: validation.value.method,
        headers: {
          Accept: 'application/json',
          ...(validation.value.body === undefined ? {} : { 'Content-Type': 'application/json' }),
          'X-A3-Desktop-Token': runtime.token,
        },
        body: validation.value.body === undefined ? undefined : JSON.stringify(validation.value.body),
      })
      return await toDesktopResponse(response)
    } catch (error) {
      await log(`backend proxy request failed: ${error instanceof Error ? error.name : 'unknown'}`)
      return { ok: false, status: 503, error: desktopError('DESKTOP_BACKEND_UNAVAILABLE', '本地学习服务暂不可用。', true) }
    }
  }
  return { request, startStream, cancelStream, cleanupWebContents, cleanupAll }
}
```

Implement `toDesktopResponse` with a bounded reader (`MAX_RESPONSE_BYTES = 5 * 1024 * 1024`). Enforce the bound before JSON parsing; preserve safe backend `{ code, message, retryable, request_id }` fields; otherwise return only a generic Chinese error. Never log token, URL query values, request bodies or response bodies. Add this test file to `package.json`'s Node test command.

- [ ] **Step 4: Run all Node tests.**

Run: `node --test electron\\runtime.test.mjs electron\\backend-lifecycle.test.mjs electron\\ipc-contract.test.mjs electron\\backend-proxy.test.mjs`

Expected: all tests pass.

### Task 3: Add SSE forwarding, ownership and cancellation

**Files:**

- Modify: `electron/backend-proxy.mjs`
- Modify: `electron/backend-proxy.test.mjs`

- [ ] **Step 1: Add failing SSE tests.**

Add tests with a chunked `ReadableStream` for each behavior:

```js
test('forwards split SSE events only to owner and finishes cleanly', async () => {
  // Split a delta JSON payload across chunks; assert owner.send('a3:stream-event',
  // { streamId, type: 'event', event: { event: 'delta', content: '你好' } }) then type: 'done'.
  // Assert activeStreamCount() is 0.
})

test('rejects duplicate IDs, foreign cancellation and more than four owner streams', async () => {
  // Assert a safe error event and prove a foreign AbortController was not aborted.
})

test('aborts and removes streams on cancel, owner destruction and backend cleanup', async () => {
  // Assert controller.signal.aborted and activeStreamCount() is 0 for all three paths.
})

test('returns DESKTOP_STREAM_INVALID when unfinished SSE data exceeds 512 KiB', async () => {
  // Feed delimiter-free data over the limit and assert error then cleanup.
})
```

- [ ] **Step 2: Run the SSE test to verify it fails.**

Run: `node --test electron\\backend-proxy.test.mjs`

Expected: failures because stream ownership, parser and bounds do not exist.

- [ ] **Step 3: Implement stream registry and parser.**

Implement `startStream(event, streamId, input)` and `cancelStream(event, streamId)` in `createBackendProxy`:

1. Require a trusted sender and `validateDesktopRequest(input, { stream: true })` for only `POST /api/chat/stream`.
2. Key a Map by `${event.sender.id}:${streamId}`; reject duplicates and more than four active streams per owner.
3. Fetch with the main-only token and an AbortController; read `response.body.getReader()`.
4. Split SSE blocks on blank lines; read only `event:` and JSON `data:` fields; enforce a 256 KiB event and 512 KiB unfinished-buffer limit.
5. Send `{ streamId, type: 'event', event }`, capture `generation_id`, send `{ streamId, type: 'done' }` on completion, and send `{ streamId, type: 'error', error }` for HTTP, parse, bound or network failures.
6. Delete entries in `finally`. `cleanupWebContents(webContents)` and `cleanupAll()` abort and delete matching streams without sending to destroyed contents.

`cancelStream` must only abort the original sender's entry and return silently for foreign or completed IDs.

- [ ] **Step 4: Re-run proxy tests.**

Run: `node --test electron\\backend-proxy.test.mjs`

Expected: all normal-request and SSE tests pass.

### Task 4: Wire the main process and narrow preload

**Files:**

- Modify: `electron/main.mjs`
- Modify: `electron/preload.mjs`
- Modify: `electron/runtime.test.mjs`

- [ ] **Step 1: Write failing bridge-boundary tests.**

Extend `electron/runtime.test.mjs`:

```js
test('preload and renderer client do not contain runtime token or backend address injection', () => {
  const preload = fs.readFileSync(path.join(projectDir, 'electron', 'preload.mjs'), 'utf8')
  const client = fs.readFileSync(path.join(projectDir, 'src', 'api', 'client.ts'), 'utf8')
  assert.doesNotMatch(preload, /desktopToken|apiBaseUrl|a3:runtime-info/)
  assert.doesNotMatch(client, /desktopToken|window\.a3Desktop\?\.apiBaseUrl/)
})

test('preload exposes fixed request and stream bridge methods only', () => {
  const preload = fs.readFileSync(path.join(projectDir, 'electron', 'preload.mjs'), 'utf8')
  for (const name of ['request:', 'startStream:', 'cancelStream:', 'onStreamEvent:', 'onBackendExit:']) assert.match(preload, new RegExp(name))
  assert.doesNotMatch(preload, /openExternal|ipcRenderer\s*[,)}]/)
})
```

- [ ] **Step 2: Run the test to verify it fails.**

Run: `node --test electron\\runtime.test.mjs`

Expected: failure because current preload injects `apiBaseUrl` and `desktopToken`.

- [ ] **Step 3: Replace injection with fixed handlers.**

In `electron/main.mjs`, replace `runtimeInfo` with `backendRuntime` held only in main:

```js
let backendRuntime = null
let backendProxy = null

// After awaitBackendStartup succeeds, before createWindow:
backendRuntime = {
  baseUrl,
  token,
  indexUrl: pathToFileURL(path.join(projectDir, 'dist', 'index.html')).href,
}
backendProxy = createBackendProxy({
  getRuntime: () => backendRuntime,
  getMainWebContents: () => mainWindow?.webContents,
  log,
})
```

Register these handlers once during startup, not for each backend restart:

```js
ipcMain.handle('a3:api-request', (event, input) => backendProxy?.request(event, input)
  ?? { ok: false, status: 503, error: desktopError('DESKTOP_BACKEND_UNAVAILABLE', '本地学习服务暂不可用。', true) })
ipcMain.on('a3:stream-start', (event, streamId, input) => { void backendProxy?.startStream(event, streamId, input) })
ipcMain.on('a3:stream-cancel', (event, streamId) => backendProxy?.cancelStream(event, streamId))
```

Remove `a3:runtime-info` and `canAccessRuntimeInfo`. On backend exit, stop, before-quit, main-window destruction and denied navigation, call proxy cleanup before clearing `backendRuntime`.

Replace `electron/preload.mjs` with:

```js
import { contextBridge, ipcRenderer } from 'electron'

contextBridge.exposeInMainWorld('a3Desktop', Object.freeze({
  request: (input) => ipcRenderer.invoke('a3:api-request', input),
  startStream: (streamId, input) => ipcRenderer.send('a3:stream-start', streamId, input),
  cancelStream: (streamId) => ipcRenderer.send('a3:stream-cancel', streamId),
  onStreamEvent: (listener) => {
    const callback = (_event, message) => listener(message)
    ipcRenderer.on('a3:stream-event', callback)
    return () => ipcRenderer.removeListener('a3:stream-event', callback)
  },
  onBackendExit: (listener) => {
    const callback = (_event, payload) => listener(payload)
    ipcRenderer.on('a3:backend-exited', callback)
    return () => ipcRenderer.removeListener('a3:backend-exited', callback)
  },
}))
```

Retain `contextIsolation: true`, `nodeIntegration: false`, `sandbox: true`, existing navigation restrictions and backend process cleanup.

- [ ] **Step 4: Run Node verification.**

Run: `node --test electron\\runtime.test.mjs electron\\backend-lifecycle.test.mjs electron\\ipc-contract.test.mjs electron\\backend-proxy.test.mjs`

Expected: all tests pass and no preload value contains token or address.

### Task 5: Adapt the Vue API layer without changing business callers

**Files:**

- Create: `src/api/transport.ts`
- Create: `src/api/desktop-transport.ts`
- Create: `src/api/web-transport.ts`
- Create: `src/api/desktop-transport.test.ts`
- Create: `src/env.d.ts`
- Modify: `src/api/client.ts`
- Modify: `src/api/backend.ts`
- Modify: `src/api/index.ts`
- Modify: `src/api/backend.test.ts`

- [ ] **Step 1: Write failing desktop adapter tests.**

Create `src/api/desktop-transport.test.ts`:

```ts
it('converts desktop envelopes into typed results and user-safe errors', async () => {
  const bridge = fakeBridge({ ok: true, status: 200, data: { status: 'ready' } })
  expect(await createDesktopTransport(bridge).request({ method: 'GET', path: '/health/ready' })).toEqual({ status: 'ready' })
  bridge.request.mockResolvedValueOnce({ ok: false, status: 503, error: { code: 'DESKTOP_BACKEND_UNAVAILABLE', message: '本地学习服务暂不可用。', retryable: true } })
  await expect(createDesktopTransport(bridge).request({ method: 'GET', path: '/health/ready' })).rejects.toMatchObject({ name: 'DesktopApiError', code: 'DESKTOP_BACKEND_UNAVAILABLE' })
})

it('subscribes before start, forwards only matching events and aborts its own stream', async () => {
  const bridge = fakeBridge({ ok: true, status: 200, data: {} })
  const controller = new AbortController()
  const transport = createDesktopTransport(bridge)
  const promise = transport.stream({ method: 'POST', path: '/api/chat/stream', body: { session_id: 'student_1', message: 'hi' } }, vi.fn(), controller.signal)
  expect(bridge.onStreamEvent).toHaveBeenCalledBefore(bridge.startStream as never)
  controller.abort()
  expect(bridge.cancelStream).toHaveBeenCalledTimes(1)
  bridge.emit({ streamId: bridge.startedId, type: 'done' })
  await promise
  expect(bridge.unsubscribe).toHaveBeenCalledTimes(1)
})
```

- [ ] **Step 2: Run the test to verify it fails.**

Run: `npx vitest run src/api/desktop-transport.test.ts`

Expected: module-not-found for `desktop-transport.ts`.

- [ ] **Step 3: Implement the transport types and adapters.**

Create `src/api/transport.ts`:

```ts
import type { StreamEvent } from './types'

export interface TransportRequest {
  method: 'GET' | 'POST' | 'PUT' | 'DELETE'
  path: string
  query?: Record<string, string | number | boolean>
  body?: unknown
}

export class DesktopApiError extends Error {
  constructor(public readonly status: number, public readonly code: string, message: string, public readonly retryable = false) {
    super(message)
    this.name = 'DesktopApiError'
  }
}

export interface BackendTransport {
  request<T>(input: TransportRequest): Promise<T>
  stream(input: TransportRequest, onEvent: (event: StreamEvent) => void, signal?: AbortSignal): Promise<void>
}
```

In `src/env.d.ts`, declare only `request`, `startStream`, `cancelStream`, `onStreamEvent` and `onBackendExit` on `window.a3Desktop`; do not declare token or address properties.

`DesktopTransport.request` calls the bridge, returns `data` for `{ ok: true }`, and throws `DesktopApiError` for failures. `DesktopTransport.stream` uses `crypto.randomUUID()`, registers `onStreamEvent` before `startStream`, ignores foreign stream IDs, resolves on done, rejects error, and always unsubscribes/removes its AbortSignal listener.

`WebTransport` retains Axios/fetch direct access for browser development only. It reads `VITE_API_BASE_URL` or Vite's relative proxy, never `window.a3Desktop` fields. Move the current `parseSseBlock` and `readSseBody` into this adapter or re-export them for existing tests.

Refactor `src/api/backend.ts` so existing method names and return types remain unchanged but call selected transport. `streamChat` must send `{ method: 'POST', path: '/api/chat/stream', body: { session_id: sessionId, message } }`; `cancelGeneration` must send existing DELETE path with query `{ session_id: sessionId }`.

`src/api/client.ts` removes token interceptors, Electron globals and the production `127.0.0.1:8000` fallback. It retains only WebTransport helpers and `errorMessage`, which recognizes AxiosError and DesktopApiError.

- [ ] **Step 4: Run targeted Vitest tests.**

Run: `npx vitest run src/api/desktop-transport.test.ts src/api/backend.test.ts src/views/SmartTutor.test.ts`

Expected: all targeted tests pass.

### Task 6: Preserve page-level streaming and cancellation behavior

**Files:**

- Modify: `src/views/SmartTutor.vue`
- Modify: `src/views/SmartTutor.test.ts`
- Modify: `src/layouts/AppLayout.vue`

- [ ] **Step 1: Add failing behavior tests.**

Extend `src/views/SmartTutor.test.ts` with a stream mock that emits a generation id then rejects with `DesktopApiError(499, 'DESKTOP_STREAM_CANCELLED', '生成已取消。')` after abort:

```ts
it('treats desktop stream cancellation as cancellation and releases the generation', async () => {
  apiMock.streamChat.mockImplementation(async (_sessionId, _message, onEvent, signal) => {
    onEvent({ event: 'delta', generation_id: 'generation_1', content: '正在生成' })
    await new Promise((_, reject) => signal?.addEventListener('abort', () => reject(new DesktopApiError(499, 'DESKTOP_STREAM_CANCELLED', '生成已取消。'))))
  })
  const wrapper = mountTutor()
  await wrapper.get('textarea').setValue('测试')
  await wrapper.get('button').trigger('click')
  await wrapper.get('button[type="button"]').trigger('click')
  expect(apiMock.cancelGeneration).toHaveBeenCalledWith('generation_1', expect.any(String))
  expect(wrapper.text()).not.toContain('桌面令牌')
})
```

Add a focused AppLayout/store test that emits `onBackendExit({ code: 1 })` and asserts the visible backend state becomes unavailable without any runtime value being rendered.

- [ ] **Step 2: Run the test to verify it fails if caller logic assumes direct fetch semantics.**

Run: `npx vitest run src/views/SmartTutor.test.ts`

Expected: failure until cancellation treats the desktop cancellation error as non-fatal and releases the local stream.

- [ ] **Step 3: Make the smallest caller changes.**

Keep `AbortController` in `SmartTutor`. If `generationId` exists, call `backendApi.cancelGeneration(generationId, sessionId)` and then `controller.abort()`; ignore only `AbortError` and `DesktopApiError` code `DESKTOP_STREAM_CANCELLED` in the message error path. Do not add token, port or IPC logic to Vue components.

Keep AppLayout subscribed only to `onBackendExit`; do not add configuration fields to it.

- [ ] **Step 4: Run all tests.**

Run: `npm run test`

Expected: all Node IPC tests and Vitest suites pass.

### Task 7: Perform source-boundary, packaging and runtime verification

**Files:**

- Modify: `electron/runtime.test.mjs`
- Modify: `README.md`
- Modify: `codex/AI模型任务队列.md`

- [ ] **Step 1: Add a failing source-boundary assertion.**

Add this test to `electron/runtime.test.mjs`:

```js
test('renderer, preload and desktop bundle do not receive token or backend address', () => {
  const rendererFiles = [
    path.join(projectDir, 'electron', 'preload.mjs'),
    path.join(projectDir, 'src', 'api', 'client.ts'),
    path.join(projectDir, 'src', 'api', 'desktop-transport.ts'),
  ]
  for (const file of rendererFiles) {
    const source = fs.readFileSync(file, 'utf8')
    assert.doesNotMatch(source, /desktopToken|apiBaseUrl|X-A3-Desktop-Token/)
  }
  const emitted = fs.readdirSync(path.join(projectDir, 'dist', 'assets')).filter(name => name.endsWith('.js'))
  for (const file of emitted) assert.doesNotMatch(fs.readFileSync(path.join(projectDir, 'dist', 'assets', file), 'utf8'), /desktopToken|X-A3-Desktop-Token/)
})
```

- [ ] **Step 2: Run it to verify legacy exposure fails.**

Run: `node --test electron\\runtime.test.mjs`

Expected: failure until all token/address injection references are removed from renderer and preload code.

- [ ] **Step 3: Remove legacy documentation and update application guidance.**

Remove stale `a3:runtime-info`, `desktopToken` and `apiBaseUrl` bridge documentation. Update `README.md` to state that packaged Electron uses a main-process HTTP/SSE proxy and browser direct access is development-only. Keep the existing Vite Web History / Electron Hash History build split.

- [ ] **Step 4: Run fresh full verification.**

Run these PowerShell commands separately and require exit code 0 from each:

```powershell
npm run test
```

```powershell
npm run build
```

```powershell
npm run build:desktop
```

```powershell
$env:ELECTRON_BUILDER_BINARIES_MIRROR='https://npmmirror.com/mirrors/electron-builder-binaries/'
npm run desktop:pack
```

```powershell
$env:ELECTRON_BUILDER_BINARIES_MIRROR='https://npmmirror.com/mirrors/electron-builder-binaries/'
npm run desktop:dist
```

Expected: Web build emits `/assets/...`; desktop build emits `./assets/...`; `release\\智学协作台 Setup 0.0.0.exe` exists and is non-empty.

- [ ] **Step 5: Run the test-mode desktop process.**

Run:

```powershell
$env:A3_ELECTRON_TEST_MODE='1'
npm run desktop:dev
```

Expected: the Electron log contains `backend ready`, the process exits automatically, and `Get-Process api -ErrorAction SilentlyContinue` returns no process. If Windows prevents direct launch of the unsigned unpacked executable, record its OS error and retain this test-mode evidence; do not weaken OS security controls.

- [ ] **Step 6: Record completion.**

Update `codex/AI模型任务队列.md` with exact modified paths and verification output. Mark S-011 complete and unblock T-028 only after every preceding command has fresh success evidence.

## Plan self-review

- **Spec coverage:** Tasks 1–3 cover the allowlist, token injection, normal HTTP, SSE, bounds, cancellation, sender ownership and cleanup. Task 4 narrows main/preload. Tasks 5–6 preserve all Vue business callers and cancellation UX. Task 7 covers source exposure, builds, package generation, runtime evidence and queue handoff.
- **No placeholders:** Each task names exact files, commands, failure condition, public APIs and acceptance assertions. The absent Git repository is explicitly handled through queue records instead of commit steps.
- **Type consistency:** `DesktopRequest`/`TransportRequest` consistently use `method`, `path`, `query` and `body`. Main/preload/renderer consistently use `request`, `startStream`, `cancelStream`, `onStreamEvent` and `onBackendExit`.
