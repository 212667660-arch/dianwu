import assert from 'node:assert/strict'
import test from 'node:test'

import { createBackendProxy } from './backend-proxy.mjs'

const FIVE_MIB = 5 * 1024 * 1024

function createContext({ runtime, fetchImpl, log = async () => {}, isAiPaused = () => false } = {}) {
  const mainWebContents = { id: 1, isDestroyed: () => false, send() {} }
  const defaultRuntime = {
    baseUrl: 'http://127.0.0.1:8123/',
    token: 'main-process-token',
    indexUrl: 'file:///E:/software-cup/a3-front/dist/index.html',
  }
  const activeRuntime = runtime === undefined ? defaultRuntime : runtime
  const event = {
    sender: mainWebContents,
    senderFrame: { url: activeRuntime?.indexUrl ?? defaultRuntime.indexUrl },
  }

  return {
    event,
    mainWebContents,
    runtime: activeRuntime,
    proxy: createBackendProxy({
      getRuntime: () => activeRuntime,
      getMainWebContents: () => mainWebContents,
      fetchImpl,
      log,
      isAiPaused,
    }),
  }
}

test('AI pause blocks ordinary and streaming generation before backend contact', async () => {
  let fetchCalls = 0
  const messages = []
  const { event, mainWebContents, proxy } = createContext({
    isAiPaused: () => true,
    fetchImpl: async () => { fetchCalls += 1; return Response.json({}) },
  })
  mainWebContents.send = (_channel, payload) => messages.push(payload)

  const result = await proxy.request(event, {
    method: 'POST', path: '/api/chat', body: { session_id: 's1', message: 'hello' },
  })
  await proxy.startStream(event, 'paused_stream', {
    method: 'POST', path: '/api/chat/stream', body: { session_id: 's1', message: 'hello' },
  })

  assert.equal(result.ok, false)
  assert.equal(result.status, 423)
  assert.equal(result.error.code, 'DESKTOP_AI_PAUSED')
  assert.equal(messages[0].error.code, 'DESKTOP_AI_PAUSED')
  assert.equal(fetchCalls, 0)
})

function sseResponse(chunks, { status = 200, headers = {} } = {}) {
  const encoder = new TextEncoder()
  return new Response(new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk))
      controller.close()
    },
  }), {
    status,
    headers: { 'Content-Type': 'text/event-stream; charset=utf-8', ...headers },
  })
}

function pendingSseResponse({ onCancel } = {}) {
  return new Response(new ReadableStream({
    cancel() { onCancel?.() },
  }), {
    headers: { 'Content-Type': 'text/event-stream; charset=utf-8' },
  })
}

async function waitFor(assertion, attempts = 30) {
  let lastError
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    try {
      assertion()
      return
    } catch (error) {
      lastError = error
      await new Promise(resolve => setTimeout(resolve, 0))
    }
  }
  throw lastError
}

test('proxies a trusted health readiness request with the main-process token only', async () => {
  let call
  const { event, proxy, runtime } = createContext({
    fetchImpl: async (url, options) => {
      call = { url, options }
      return Response.json({ status: 'ready' })
    },
  })

  const result = await proxy.request(event, { method: 'GET', path: '/health/ready' })

  assert.deepEqual(result, { ok: true, status: 200, data: { status: 'ready' } })
  assert.equal(call.url, 'http://127.0.0.1:8123/health/ready')
  assert.equal(call.options.headers['X-A3-Desktop-Token'], runtime.token)
  assert.equal(call.options.headers.Accept, 'application/json')
  assert.equal(call.options.headers['Content-Type'], undefined)
  assert.equal(call.url.includes(runtime.token), false)
})

test('rejects a foreign sender without contacting the backend', async () => {
  let fetchCalls = 0
  const { event, mainWebContents, proxy } = createContext({
    fetchImpl: async () => {
      fetchCalls += 1
      return Response.json({ status: 'ready' })
    },
  })
  event.sender = { isDestroyed: () => false }
  assert.notEqual(event.sender, mainWebContents)

  const result = await proxy.request(event, { method: 'GET', path: '/health/ready' })

  assert.deepEqual(result, {
    ok: false,
    status: 403,
    error: {
      code: 'DESKTOP_REQUEST_DENIED',
      message: '桌面请求未获授权。',
      retryable: false,
    },
  })
  assert.equal(fetchCalls, 0)
})

test('rejects requests when the backend runtime is unavailable without contacting the backend', async () => {
  let fetchCalls = 0
  const { event, proxy } = createContext({
    runtime: null,
    fetchImpl: async () => {
      fetchCalls += 1
      return Response.json({ status: 'ready' })
    },
  })

  const result = await proxy.request(event, { method: 'GET', path: '/health/ready' })

  assert.deepEqual(result, {
    ok: false,
    status: 403,
    error: {
      code: 'DESKTOP_REQUEST_DENIED',
      message: '桌面请求未获授权。',
      retryable: false,
    },
  })
  assert.equal(fetchCalls, 0)
})

test('rejects invalid renderer transport inputs and routes before contacting the backend', async () => {
  let fetchCalls = 0
  const rendererToken = 'renderer-forged-token'
  const { event, proxy, runtime } = createContext({
    fetchImpl: async () => {
      fetchCalls += 1
      return Response.json({ status: 'ready' })
    },
  })
  const invalidRequests = [
    {
      method: 'GET',
      path: '/health/ready',
      headers: {
        Authorization: `Bearer ${rendererToken}`,
        'X-A3-Desktop-Token': rendererToken,
      },
      token: rendererToken,
    },
    { method: 'GET', path: '/api/admin' },
    { method: 'GET', path: 'https://attacker.example/health/ready' },
  ]

  assert.notEqual(rendererToken, runtime.token)
  for (const input of invalidRequests) {
    const result = await proxy.request(event, input)

    assert.equal(result.ok, false)
    assert.equal(result.status, 400)
    assert.equal(result.error.code, 'DESKTOP_REQUEST_DENIED')
    assert.equal(fetchCalls, 0)
  }
})

test('rejects renderer authentication lookalikes before contacting the backend', async () => {
  let call
  const rendererToken = 'renderer-forged-token'
  const { event, proxy, runtime } = createContext({
    fetchImpl: async (url, options) => {
      call = { url, options }
      return Response.json({ accepted: true })
    },
  })

  const result = await proxy.request(event, {
    method: 'POST',
    path: '/api/chat',
    body: {
      session_id: 'student_1',
      message: 'hello',
      token: rendererToken,
      headers: {
        Authorization: `Bearer ${rendererToken}`,
        'X-A3-Desktop-Token': rendererToken,
      },
    },
  })

  assert.equal(result.ok, false)
  assert.equal(result.status, 400)
  assert.equal(result.error.code, 'DESKTOP_REQUEST_DENIED')
  assert.equal(call, undefined)
  assert.notEqual(rendererToken, runtime.token)
})

test('retains structured backend error metadata from a 401 response', async () => {
  const { event, proxy } = createContext({
    fetchImpl: async () => new Response(JSON.stringify({
      code: 'MODEL_AUTHENTICATION_ERROR',
      message: '模型访问凭据无效。',
      retryable: false,
      request_id: 'backend-request-42',
    }), {
      status: 401,
      headers: { 'Content-Type': 'application/json' },
    }),
  })

  const result = await proxy.request(event, { method: 'GET', path: '/health/ready' })

  assert.deepEqual(result, {
    ok: false,
    status: 401,
    error: {
      code: 'MODEL_AUTHENTICATION_ERROR',
      message: '模型访问凭据无效。',
      retryable: false,
      requestId: 'backend-request-42',
    },
  })
})

test('preserves canonical 404, 422, and 503 backend error envelopes', async () => {
  for (const [status, code, retryable] of [
    [404, 'SESSION_NOT_FOUND', false],
    [422, 'REQUEST_VALIDATION_ERROR', false],
    [503, 'MODEL_NOT_READY', false],
  ]) {
    const { event, proxy } = createContext({
      fetchImpl: async () => new Response(JSON.stringify({
        code,
        message: '安全错误文案。',
        retryable,
        request_id: 'req-contract',
      }), {
        status,
        headers: { 'Content-Type': 'application/json' },
      }),
    })

    const result = await proxy.request(event, { method: 'GET', path: '/health/ready' })

    assert.deepEqual(result, {
      ok: false,
      status,
      error: {
        code,
        message: '安全错误文案。',
        retryable,
        requestId: 'req-contract',
      },
    })
  }
})

test('preserves canonical HTTP status for stream setup failures', async () => {
  for (const [status, code, retryable] of [
    [404, 'SESSION_NOT_FOUND', false],
    [422, 'REQUEST_VALIDATION_ERROR', false],
    [503, 'MODEL_NOT_READY', false],
  ]) {
    const messages = []
    const { event, mainWebContents, proxy } = createContext({
      fetchImpl: async () => new Response(JSON.stringify({
        code,
        message: '安全错误文案。',
        retryable,
        request_id: 'req-stream-contract',
      }), {
        status,
        headers: { 'Content-Type': 'application/json' },
      }),
    })
    mainWebContents.send = (_channel, message) => messages.push(message)

    await proxy.startStream(event, `stream_contract_${status}`, {
      method: 'POST',
      path: '/api/chat/stream',
      body: { session_id: 'student_1', message: 'hello' },
    })

    assert.deepEqual(messages, [{
      streamId: `stream_contract_${status}`,
      type: 'error',
      status,
      error: {
        code,
        message: '安全错误文案。',
        retryable,
        requestId: 'req-stream-contract',
      },
    }])
  }
})

test('rejects an incomplete backend error envelope without exposing its body', async () => {
  const { event, proxy } = createContext({
    fetchImpl: async () => new Response(JSON.stringify({
      code: 'SESSION_NOT_FOUND',
      message: 'private upstream detail',
      request_id: 'req-incomplete',
    }), {
      status: 404,
      headers: { 'Content-Type': 'application/json' },
    }),
  })

  const result = await proxy.request(event, { method: 'GET', path: '/health/ready' })

  assert.deepEqual(result, {
    ok: false,
    status: 404,
    error: {
      code: 'DESKTOP_BACKEND_HTTP_ERROR',
      message: '本地服务请求未成功。',
      retryable: false,
    },
  })
  assert.equal(JSON.stringify(result).includes('private upstream detail'), false)
})

test('maps a non-JSON HTTP error to a safe generic envelope', async () => {
  const upstreamSecret = 'private upstream diagnostic details'
  const { event, proxy } = createContext({
    fetchImpl: async () => new Response(upstreamSecret, {
      status: 500,
      headers: { 'Content-Type': 'text/plain' },
    }),
  })

  const result = await proxy.request(event, { method: 'GET', path: '/health/ready' })

  assert.deepEqual(result, {
    ok: false,
    status: 500,
    error: {
      code: 'DESKTOP_BACKEND_HTTP_ERROR',
      message: '本地服务请求未成功。',
      retryable: true,
    },
  })
  assert.equal(JSON.stringify(result).includes(upstreamSecret), false)
})

test('maps malformed JSON from a successful response to a safe generic envelope', async () => {
  const malformedBody = '{"secret":"private malformed response"'
  const { event, proxy } = createContext({
    fetchImpl: async () => new Response(malformedBody, {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }),
  })

  const result = await proxy.request(event, { method: 'GET', path: '/health/ready' })

  assert.deepEqual(result, {
    ok: false,
    status: 502,
    error: {
      code: 'DESKTOP_BACKEND_RESPONSE_INVALID',
      message: '本地服务响应格式无效。',
      retryable: true,
    },
  })
  assert.equal(JSON.stringify(result).includes(malformedBody), false)
})

test('returns and logs a redacted envelope when fetch fails', async () => {
  const logEntries = []
  const { event, proxy, runtime } = createContext({
    fetchImpl: async () => {
      const error = new Error('connection failed')
      error.name = 'AbortError'
      throw error
    },
    log: async (entry) => { logEntries.push(entry) },
  })

  const result = await proxy.request(event, { method: 'GET', path: '/health/ready', query: { trace: 'private' } })
  const serialized = JSON.stringify({ result, logEntries })

  assert.equal(result.status, 503)
  assert.equal(result.error.code, 'DESKTOP_BACKEND_UNAVAILABLE')
  assert.equal(result.error.retryable, true)
  assert.equal(logEntries.length, 1)
  assert.equal(logEntries[0].errorName, 'AbortError')
  assert.equal(serialized.includes(runtime.baseUrl), false)
  assert.equal(serialized.includes(runtime.token), false)
  assert.equal(serialized.includes('trace=private'), false)
})

test('redacts runtime and JSON-body secrets from fetch failure envelopes and logs', async () => {
  const runtime = {
    baseUrl: 'http://127.0.0.1:9123/',
    token: 'main-token-private-value',
    indexUrl: 'file:///E:/software-cup/a3-front/dist/index.html',
  }
  const body = {
    message: 'hello',
    secret: 'json-body-private-value',
  }
  const bodyJson = JSON.stringify(body)
  const logEntries = []
  let thrownError
  const { event, proxy } = createContext({
    runtime,
    fetchImpl: async () => {
      thrownError = new Error(`failed ${runtime.baseUrl} token=${runtime.token} body=${bodyJson}`)
      thrownError.name = `SecretError:${runtime.baseUrl}:${runtime.token}:${bodyJson}`
      throw thrownError
    },
    log: async (entry) => { logEntries.push(entry) },
  })

  const result = await proxy.request(event, { method: 'POST', path: '/api/knowledge/search', body })
  const serialized = JSON.stringify({ result, logEntries })

  assert.deepEqual(result, {
    ok: false,
    status: 503,
    error: {
      code: 'DESKTOP_BACKEND_UNAVAILABLE',
      message: '本地服务暂时不可用，请稍后重试。',
      retryable: true,
    },
  })
  assert.deepEqual(logEntries, [{
    event: 'desktop-backend-fetch-failed',
    errorName: 'UnknownError',
  }])
  for (const secret of [runtime.baseUrl, runtime.token, body.secret, bodyJson, thrownError.message, thrownError.name]) {
    assert.equal(serialized.includes(secret), false)
  }
})

test('rejects a JSON literal from a successful non-JSON response', async () => {
  const { event, proxy } = createContext({
    fetchImpl: async () => new Response('{"accepted":true}', {
      status: 200,
      headers: { 'Content-Type': 'text/html; charset=utf-8' },
    }),
  })

  const result = await proxy.request(event, { method: 'GET', path: '/health/ready' })

  assert.equal(result.ok, false)
  assert.equal(result.status, 502)
  assert.equal(result.error.code, 'DESKTOP_BACKEND_RESPONSE_INVALID')
  assert.equal(JSON.stringify(result).includes('accepted'), false)
})

test('accepts a successful application problem JSON response', async () => {
  const { event, proxy } = createContext({
    fetchImpl: async () => new Response('{"status":"ready"}', {
      status: 200,
      headers: { 'Content-Type': 'application/problem+json; charset=utf-8' },
    }),
  })

  const result = await proxy.request(event, { method: 'GET', path: '/health/ready' })

  assert.deepEqual(result, { ok: true, status: 200, data: { status: 'ready' } })
})

test('rejects invalid UTF-8 instead of parsing replacement characters', async () => {
  const invalidUtf8Json = new Uint8Array([
    0x7b, 0x22, 0x76, 0x61, 0x6c, 0x75, 0x65, 0x22, 0x3a, 0x22,
    0xc3, 0x28,
    0x22, 0x7d,
  ])
  const { event, proxy } = createContext({
    fetchImpl: async () => new Response(invalidUtf8Json, {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }),
  })

  const result = await proxy.request(event, { method: 'GET', path: '/health/ready' })

  assert.equal(result.ok, false)
  assert.equal(result.status, 502)
  assert.equal(result.error.code, 'DESKTOP_BACKEND_RESPONSE_INVALID')
  assert.equal(JSON.stringify(result).includes('\ufffd'), false)
})

test('cancels a response body immediately when content-length exceeds five MiB', async () => {
  let cancelled = false
  const body = new ReadableStream({
    cancel() {
      cancelled = true
    },
  })
  const response = new Response(body, {
    status: 200,
    headers: {
      'Content-Type': 'application/json',
      'Content-Length': String(FIVE_MIB + 1),
    },
  })
  const { event, proxy } = createContext({ fetchImpl: async () => response })

  const result = await proxy.request(event, { method: 'GET', path: '/health/ready' })

  assert.equal(result.error.code, 'DESKTOP_RESPONSE_TOO_LARGE')
  assert.equal(cancelled, true)
  assert.equal(response.body.locked, false)
})

test('cancels and unlocks a response body that grows beyond five MiB', async () => {
  let cancelled = false
  const largeBody = new ReadableStream({
    start(controller) {
      controller.enqueue(new Uint8Array(FIVE_MIB + 1))
    },
    cancel() {
      cancelled = true
    },
  })
  const response = new Response(largeBody, {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })
  const { event, proxy } = createContext({
    fetchImpl: async () => response,
  })

  const result = await proxy.request(event, { method: 'GET', path: '/health/ready' })

  assert.deepEqual(result, {
    ok: false,
    status: 502,
    error: {
      code: 'DESKTOP_RESPONSE_TOO_LARGE',
      message: '本地服务响应过大，无法处理。',
      retryable: false,
    },
  })
  assert.equal(cancelled, true)
  assert.equal(response.body.locked, false)
})

test('releases the response reader lock when reading throws', async () => {
  const readError = new Error('private upstream read failure')
  const body = new ReadableStream({
    pull(controller) {
      controller.error(readError)
    },
  })
  const response = new Response(body, {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })
  const { event, proxy } = createContext({ fetchImpl: async () => response })

  const result = await proxy.request(event, { method: 'GET', path: '/health/ready' })

  assert.equal(result.ok, false)
  assert.equal(result.status, 502)
  assert.equal(result.error.code, 'DESKTOP_BACKEND_RESPONSE_INVALID')
  assert.equal(JSON.stringify(result).includes(readError.message), false)
  assert.equal(response.body.locked, false)
  const reader = response.body.getReader()
  reader.releaseLock()
})

test('forwards split SSE events only to the owner and removes the finished stream', async () => {
  const messages = []
  const { event, mainWebContents, proxy, runtime } = createContext({
    fetchImpl: async (_url, options) => {
      assert.equal(options.headers['X-A3-Desktop-Token'], runtime.token)
      assert.equal(options.headers.Accept, 'text/event-stream')
      return sseResponse([
        'event: delta\ndata: {\"content\":\"',
        '你好\",\"generation_id\":\"generation_1\"}\n\n',
        'event: done\ndata: {\"state\":\"DIAGNOSING\"}\n\n',
      ])
    },
  })
  mainWebContents.send = (channel, message) => messages.push({ channel, message })

  await proxy.startStream(event, 'stream_1', {
    method: 'POST',
    path: '/api/chat/stream',
    body: { session_id: 'student_1', message: 'hello' },
  })

  assert.deepEqual(messages, [
    {
      channel: 'a3:stream-event',
      message: {
        streamId: 'stream_1',
        type: 'event',
        event: { event: 'delta', content: '你好', generation_id: 'generation_1' },
      },
    },
    {
      channel: 'a3:stream-event',
      message: {
        streamId: 'stream_1',
        type: 'event',
        event: { event: 'done', state: 'DIAGNOSING' },
      },
    },
    { channel: 'a3:stream-event', message: { streamId: 'stream_1', type: 'done' } },
  ])
  assert.equal(proxy.activeStreamCount(), 0)
})

test('rejects duplicate IDs and more than four owner streams without allowing foreign cancellation', async () => {
  const messages = []
  const cancelled = []
  const { event, mainWebContents, proxy } = createContext({
    fetchImpl: async () => pendingSseResponse({ onCancel: () => cancelled.push(true) }),
  })
  mainWebContents.send = (channel, message) => messages.push({ channel, message })

  const first = proxy.startStream(event, 'duplicate_id', {
    method: 'POST', path: '/api/chat/stream', body: { session_id: 'student_1', message: 'first' },
  })
  await waitFor(() => assert.equal(proxy.activeStreamCount(), 1))
  await proxy.startStream(event, 'duplicate_id', {
    method: 'POST', path: '/api/chat/stream', body: { session_id: 'student_1', message: 'second' },
  })

  const foreignEvent = {
    sender: { id: 2, isDestroyed: () => false, send() {} },
    senderFrame: { url: event.senderFrame.url },
  }
  proxy.cancelStream(foreignEvent, 'duplicate_id')
  assert.equal(cancelled.length, 0)

  const extra = []
  for (const id of ['stream_2', 'stream_3', 'stream_4']) {
    extra.push(proxy.startStream(event, id, {
      method: 'POST', path: '/api/chat/stream', body: { session_id: 'student_1', message: id },
    }))
  }
  await waitFor(() => assert.equal(proxy.activeStreamCount(), 4))
  await proxy.startStream(event, 'stream_5', {
    method: 'POST', path: '/api/chat/stream', body: { session_id: 'student_1', message: 'limited' },
  })

  assert.deepEqual(messages.map(item => item.message), [
    {
      streamId: 'duplicate_id',
      type: 'error',
      error: { code: 'DESKTOP_STREAM_INVALID', message: '流式请求标识无效。', retryable: false },
    },
    {
      streamId: 'stream_5',
      type: 'error',
      error: { code: 'DESKTOP_STREAM_LIMITED', message: '当前窗口的流式请求数量已达上限。', retryable: true },
    },
  ])

  proxy.cleanupAll()
  await Promise.all([first, ...extra])
  assert.equal(cancelled.length, 4)
  assert.equal(proxy.activeStreamCount(), 0)
})

test('aborts and removes streams on cancellation, owner destruction, and backend cleanup', async () => {
  const cancelled = []
  const { event, mainWebContents, proxy } = createContext({
    fetchImpl: async () => pendingSseResponse({ onCancel: () => cancelled.push(true) }),
  })

  const cancelledByOwner = proxy.startStream(event, 'cancelled_by_owner', {
    method: 'POST', path: '/api/chat/stream', body: { session_id: 'student_1', message: 'one' },
  })
  await waitFor(() => assert.equal(proxy.activeStreamCount(), 1))
  proxy.cancelStream(event, 'cancelled_by_owner')
  await cancelledByOwner
  assert.equal(proxy.activeStreamCount(), 0)

  const destroyedOwner = proxy.startStream(event, 'destroyed_owner', {
    method: 'POST', path: '/api/chat/stream', body: { session_id: 'student_1', message: 'two' },
  })
  await waitFor(() => assert.equal(proxy.activeStreamCount(), 1))
  proxy.cleanupWebContents(mainWebContents)
  await destroyedOwner
  assert.equal(proxy.activeStreamCount(), 0)

  const backendStopped = proxy.startStream(event, 'backend_stopped', {
    method: 'POST', path: '/api/chat/stream', body: { session_id: 'student_1', message: 'three' },
  })
  await waitFor(() => assert.equal(proxy.activeStreamCount(), 1))
  proxy.cleanupAll()
  await backendStopped
  assert.equal(cancelled.length, 3)
  assert.equal(proxy.activeStreamCount(), 0)
})

test('emits a safe invalid-stream error when unfinished SSE data exceeds 512 KiB', async () => {
  const messages = []
  const { event, mainWebContents, proxy } = createContext({
    fetchImpl: async () => sseResponse(['x'.repeat(512 * 1024 + 1)]),
  })
  mainWebContents.send = (_channel, message) => messages.push(message)

  await proxy.startStream(event, 'oversized_buffer', {
    method: 'POST', path: '/api/chat/stream', body: { session_id: 'student_1', message: 'overflow' },
  })

  assert.deepEqual(messages, [{
    streamId: 'oversized_buffer',
    type: 'error',
    error: { code: 'DESKTOP_STREAM_INVALID', message: '流式响应数据无效。', retryable: true },
  }])
  assert.equal(proxy.activeStreamCount(), 0)
})

test('permits only the chat streaming route through the SSE entrypoint', async () => {
  const messages = []
  let fetchCalls = 0
  const { event, mainWebContents, proxy } = createContext({
    fetchImpl: async () => {
      fetchCalls += 1
      return sseResponse([])
    },
  })
  mainWebContents.send = (_channel, message) => messages.push(message)

  await proxy.startStream(event, 'ordinary_route', { method: 'GET', path: '/health/ready' })

  assert.equal(fetchCalls, 0)
  assert.deepEqual(messages, [{
    streamId: 'ordinary_route',
    type: 'error',
    error: { code: 'DESKTOP_REQUEST_DENIED', message: '流式请求仅允许聊天流接口。', retryable: false },
  }])
})
