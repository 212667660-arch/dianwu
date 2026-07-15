import assert from 'node:assert/strict'
import test from 'node:test'

import {
  buildBackendUrl,
  desktopError,
  isTrustedDesktopSender,
  validateKnowledgeCollectionId,
  validateKnowledgeDroppedPaths,
  validateKnowledgeLocator,
  validateModelConfigInput,
  validateDesktopRequest,
} from './ipc-contract.mjs'

const validModelConfig = {
  provider: 'openai',
  api_key: 'test-secret-key',
  base_url: 'https://api.example.test',
  model_name: 'test-model',
  anthropic_version: '2023-06-01',
  request_timeout_seconds: 60,
}

function expectAccepted(input, options) {
  const result = validateDesktopRequest(input, options)
  assert.equal(result.ok, true, JSON.stringify(result))
  return result.value
}

function expectRejected(input, options, code) {
  const result = validateDesktopRequest(input, options)
  assert.equal(result.ok, false, JSON.stringify(result))
  assert.equal(result.error.code, code)
}

test('模型配置候选只接受固定字段并拒绝安全边界字段', () => {
  const accepted = validateModelConfigInput(validModelConfig)
  assert.equal(accepted.ok, true, JSON.stringify(accepted))
  assert.deepEqual(accepted.value, validModelConfig)

  for (const [field, value] of Object.entries({
    headers: { authorization: 'secret' },
    token: 'secret',
    filePath: 'C:\\secret',
    baseUrl: 'https://attacker.example',
  })) {
    const result = validateModelConfigInput({ ...validModelConfig, [field]: value })
    assert.equal(result.ok, false, JSON.stringify(result))
    assert.equal(result.error.code, 'DESKTOP_REQUEST_DENIED')
  }
})

test('模型配置候选拒绝非法 provider、地址、超时和控制字符', () => {
  for (const input of [
    { ...validModelConfig, provider: 'unknown' },
    { ...validModelConfig, base_url: 'file:///secret' },
    { ...validModelConfig, request_timeout_seconds: Number.NaN },
    { ...validModelConfig, model_name: 'bad\nmodel' },
  ]) {
    const result = validateModelConfigInput(input)
    assert.equal(result.ok, false, JSON.stringify(result))
    assert.equal(result.error.code, 'DESKTOP_REQUEST_INVALID')
  }
})

test('知识库固定 IPC 只接受集合 ID 和 preload 解析的有限路径批次', () => {
  assert.deepEqual(validateKnowledgeCollectionId(7), { ok: true, value: 7 })
  assert.equal(validateKnowledgeCollectionId(0).ok, false)
  assert.equal(validateKnowledgeCollectionId('7').ok, false)

  const accepted = validateKnowledgeDroppedPaths({
    collectionId: 7,
    paths: ['C:\\资料\\lesson.pdf', 'C:\\资料\\notes.md'],
  })
  assert.equal(accepted.ok, true, JSON.stringify(accepted))
  assert.deepEqual(accepted.value, {
    collectionId: 7,
    paths: ['C:\\资料\\lesson.pdf', 'C:\\资料\\notes.md'],
  })
  for (const input of [
    { collectionId: 7, paths: [] },
    { collectionId: 7, paths: Array.from({ length: 51 }, () => 'C:\\资料\\lesson.pdf') },
    { collectionId: 7, paths: ['bad\0path'] },
    { collectionId: 7, paths: [7] },
    { collectionId: 7, paths: ['C:\\资料\\lesson.pdf'], token: 'secret' },
  ]) {
    assert.equal(validateKnowledgeDroppedPaths(input).ok, false)
  }
})

test('知识库定位只允许固定类型和正向范围', () => {
  assert.deepEqual(
    validateKnowledgeLocator({ type: 'page', start: 2, end: 3 }),
    { ok: true, value: { type: 'page', start: 2, end: 3 } },
  )
  assert.deepEqual(
    validateKnowledgeLocator({ type: 'sheet_rows', start: 4, end: 8, sheet_name: 'Sheet1' }),
    {
      ok: true,
      value: { type: 'sheet_rows', start: 4, end: 8, sheet_name: 'Sheet1' },
    },
  )
  for (const input of [
    { type: 'file', start: 1, end: 1 },
    { type: 'page', start: 0, end: 1 },
    { type: 'page', start: 2, end: 1 },
    { type: 'sheet_rows', start: 1, end: 2 },
    { type: 'page', start: 1, end: 1, path: 'C:\\secret' },
  ]) {
    assert.equal(validateKnowledgeLocator(input).ok, false)
  }
})

test('normalizes scalar reviews query values for an allowed session route', () => {
  const value = expectAccepted({
    method: 'GET',
    path: '/api/sessions/session_42/reviews',
    query: { due_only: true, limit: 10, topic: 'algebra' },
  })

  assert.deepEqual(value, {
    method: 'GET',
    path: '/api/sessions/session_42/reviews',
    query: { due_only: 'true', limit: '10', topic: 'algebra' },
    body: undefined,
    stream: false,
  })
})

test('permits the streaming chat route only when stream mode is explicitly enabled', () => {
  expectRejected(
    { method: 'POST', path: '/api/chat/stream' },
    undefined,
    'DESKTOP_REQUEST_DENIED',
  )

  const value = expectAccepted(
    { method: 'POST', path: '/api/chat/stream', body: { message: 'hello' } },
    { stream: true },
  )
  assert.equal(value.stream, true)
})

test('applies independent encoded-query and JSON-body byte limits', () => {
  expectAccepted({
    method: 'POST',
    path: '/api/chat',
    query: { q: 'x'.repeat(65_534) },
    body: 'x'.repeat(65_534),
  })
  expectRejected(
    { method: 'GET', path: '/api/sessions/session_42/reviews', query: { q: 'x'.repeat(65_535) } },
    undefined,
    'DESKTOP_REQUEST_INVALID',
  )
  expectRejected(
    { method: 'POST', path: '/api/chat', body: 'x'.repeat(65_535) },
    undefined,
    'DESKTOP_REQUEST_INVALID',
  )
})

test('rejects non-JSON body values while retaining valid absent and JSON bodies', () => {
  const circular = {}
  circular.self = circular

  for (const body of [() => {}, Symbol('body'), 1n, circular]) {
    expectRejected(
      { method: 'POST', path: '/api/chat', body },
      undefined,
      'DESKTOP_REQUEST_INVALID',
    )
  }

  assert.equal(expectAccepted({ method: 'POST', path: '/api/chat' }).body, undefined)
  assert.equal(expectAccepted({ method: 'POST', path: '/api/chat', body: undefined }).body, undefined)
  assert.equal(expectAccepted({ method: 'POST', path: '/api/chat', body: null }).body, null)
  assert.deepEqual(
    expectAccepted({ method: 'POST', path: '/api/chat', body: { message: 'valid JSON' } }).body,
    { message: 'valid JSON' },
  )
})

test('rejects external paths, traversal, unknown routes, headers, and oversized JSON bodies', () => {
  expectRejected(
    { method: 'POST', path: 'https://example.test/api/chat' },
    undefined,
    'DESKTOP_REQUEST_DENIED',
  )
  expectRejected(
    { method: 'GET', path: '/api/sessions/session_42/../progress' },
    undefined,
    'DESKTOP_REQUEST_DENIED',
  )
  expectRejected(
    { method: 'GET', path: '/api/admin' },
    undefined,
    'DESKTOP_REQUEST_DENIED',
  )
  expectRejected(
    { method: 'GET', path: '/internal/model-runtime/status' },
    undefined,
    'DESKTOP_REQUEST_DENIED',
  )
  expectRejected(
    { method: 'POST', path: '/api/chat', headers: { authorization: 'secret' } },
    undefined,
    'DESKTOP_REQUEST_DENIED',
  )
  expectRejected(
    { method: 'POST', path: '/api/chat', body: { message: 'x'.repeat(65_537) } },
    undefined,
    'DESKTOP_REQUEST_INVALID',
  )
})

test('accepts every whitelisted route and rejects a wrong method for each one', () => {
  const routes = [
    { method: 'GET', path: '/health/live' },
    { method: 'GET', path: '/health/ready' },
    { method: 'GET', path: '/api/settings/model' },
    { method: 'POST', path: '/api/chat' },
    { method: 'POST', path: '/api/chat/stream', options: { stream: true } },
    { method: 'GET', path: '/api/knowledge/status' },
    { method: 'GET', path: '/api/knowledge/collections' },
    { method: 'POST', path: '/api/knowledge/collections' },
    { method: 'PUT', path: '/api/knowledge/collections/7' },
    { method: 'DELETE', path: '/api/knowledge/collections/7' },
    { method: 'GET', path: '/api/knowledge/documents' },
    { method: 'DELETE', path: '/api/knowledge/documents/7' },
    { method: 'POST', path: '/api/knowledge/documents/7/rebuild' },
    { method: 'POST', path: '/api/knowledge/imports' },
    { method: 'GET', path: '/api/knowledge/imports/7' },
    { method: 'DELETE', path: '/api/knowledge/imports/7' },
    { method: 'POST', path: '/api/knowledge/search' },
    { method: 'GET', path: '/api/sessions/session_42' },
    { method: 'GET', path: '/api/sessions/session_42/progress' },
    { method: 'GET', path: '/api/sessions/session_42/next-action' },
    { method: 'GET', path: '/api/sessions/session_42/reviews' },
    { method: 'GET', path: '/api/sessions/session_42/mistakes' },
    { method: 'GET', path: '/api/sessions/session_42/knowledge-collections' },
    { method: 'PUT', path: '/api/sessions/session_42/knowledge-collections' },
    { method: 'POST', path: '/api/sessions/session_42/rediagnose' },
    { method: 'POST', path: '/api/sessions/session_42/questions/7/attempts' },
    { method: 'DELETE', path: '/api/generations/generation_123', query: { session_id: 'session_42' } },
  ]

  for (const route of routes) {
    const request = {
      method: route.method,
      path: route.path,
      ...(route.query === undefined ? {} : { query: route.query }),
    }
    expectAccepted(request, route.options)
    expectRejected({ ...request, method: 'PATCH' }, route.options, 'DESKTOP_REQUEST_DENIED')
  }
})

test('rejects every forbidden transport field before routing the request', () => {
  for (const [field, value] of Object.entries({
    headers: { authorization: 'secret' },
    url: 'https://example.test/api/chat',
    baseUrl: 'https://example.test',
    token: 'secret',
  })) {
    expectRejected(
      { method: 'POST', path: '/api/chat', [field]: value },
      undefined,
      'DESKTOP_REQUEST_DENIED',
    )
  }
})

test('rejects encoded traversal characters, backslashes, fragments, and non-scalar query values', () => {
  for (const path of [
    '/api/sessions/session%2e42/reviews',
    '/api/sessions/session%2f42/reviews',
    '/api/sessions/session%5c42/reviews',
    '/api/sessions/session_42\\reviews',
    '/api/sessions/session_42/reviews#fragment',
  ]) {
    expectRejected({ method: 'GET', path }, undefined, 'DESKTOP_REQUEST_DENIED')
  }

  for (const query of [
    { due_only: ['true'] },
    { due_only: { value: true } },
    { due_only: null },
  ]) {
    expectRejected(
      { method: 'GET', path: '/api/sessions/session_42/reviews', query },
      undefined,
      'DESKTOP_REQUEST_INVALID',
    )
  }
})

test('requires the main non-destroyed web contents and the index frame URL with an optional hash route', () => {
  const indexUrl = 'file:///E:/software-cup/a3-front/dist/index.html'
  const owner = { isDestroyed: () => false }
  const trustedEvent = { sender: owner, senderFrame: { url: indexUrl } }

  assert.equal(isTrustedDesktopSender(trustedEvent, owner, indexUrl), true)
  assert.equal(
    isTrustedDesktopSender(
      { sender: owner, senderFrame: { url: `${indexUrl}#/dashboard` } },
      owner,
      `${indexUrl}#boot`,
    ),
    true,
  )
  assert.equal(
    isTrustedDesktopSender({ sender: owner, senderFrame: { url: `${indexUrl}?next=dashboard` } }, owner, indexUrl),
    false,
  )
  assert.equal(
    isTrustedDesktopSender({ ...trustedEvent, sender: { isDestroyed: () => false } }, owner, indexUrl),
    false,
  )
  assert.equal(
    isTrustedDesktopSender({ sender: owner, senderFrame: { url: 'file:///E:/software-cup/a3-front/dist/other.html' } }, owner, indexUrl),
    false,
  )
  assert.equal(
    isTrustedDesktopSender({ sender: owner, senderFrame: { url: indexUrl } }, { isDestroyed: () => true }, indexUrl),
    false,
  )
  const destroyedOwner = { isDestroyed: () => true }
  assert.equal(isTrustedDesktopSender({ sender: destroyedOwner, senderFrame: { url: indexUrl } }, destroyedOwner, indexUrl), false)
  assert.equal(isTrustedDesktopSender(null, owner, indexUrl), false)
  assert.equal(isTrustedDesktopSender({ sender: owner }, owner, indexUrl), false)
  assert.equal(isTrustedDesktopSender({ sender: owner, senderFrame: { url: 'not a url' } }, owner, indexUrl), false)
  assert.equal(isTrustedDesktopSender(trustedEvent, owner, 'not a url'), false)
  const throwingOwner = { isDestroyed: () => { throw new Error('destroy-state unavailable') } }
  assert.doesNotThrow(() => {
    assert.equal(
      isTrustedDesktopSender({ sender: throwingOwner, senderFrame: { url: indexUrl } }, throwingOwner, indexUrl),
      false,
    )
  })
})

test('validates cancellation query ownership and builds a correctly encoded backend URL', () => {
  const cancel = expectAccepted({
    method: 'DELETE',
    path: '/api/generations/generation_123',
    query: { session_id: 'session-123' },
  })

  assert.equal(
    buildBackendUrl('http://127.0.0.1:8123/', cancel),
    'http://127.0.0.1:8123/api/generations/generation_123?session_id=session-123',
  )
  expectRejected(
    { method: 'DELETE', path: '/api/generations/generation_123', query: {} },
    undefined,
    'DESKTOP_REQUEST_INVALID',
  )
  expectRejected(
    {
      method: 'DELETE',
      path: '/api/generations/generation_123',
      query: { session_id: 'session-123', extra: 'no' },
    },
    undefined,
    'DESKTOP_REQUEST_DENIED',
  )
  expectRejected(
    { method: 'DELETE', path: '/api/generations/generation_123', query: { session_id: '../other' } },
    undefined,
    'DESKTOP_REQUEST_INVALID',
  )

  const reviews = expectAccepted({
    method: 'GET',
    path: '/api/sessions/session_42/reviews',
    query: { filter: 'today & tomorrow' },
  })
  assert.equal(
    buildBackendUrl('http://127.0.0.1:8123/', reviews),
    'http://127.0.0.1:8123/api/sessions/session_42/reviews?filter=today+%26+tomorrow',
  )
})

test('buildBackendUrl only accepts values returned by request validation', () => {
  const rawRequest = {
    method: 'GET',
    path: '/api/sessions/session_42/reviews',
    query: { filter: 'today & tomorrow', due_only: true },
    headers: { authorization: 'secret' },
    url: 'https://attacker.example/api/chat',
    baseUrl: 'https://attacker.example',
    token: 'secret',
  }

  assert.throws(
    () => buildBackendUrl('http://127.0.0.1:8123/', rawRequest),
    /validated desktop request/i,
  )
  assert.throws(
    () => buildBackendUrl('http://127.0.0.1:8123/', {
      method: 'GET',
      path: '/api/sessions/session_42/reviews',
      query: { filter: 'today & tomorrow', due_only: true },
      body: undefined,
      stream: false,
    }),
    /validated desktop request/i,
  )

  const validated = expectAccepted({
    method: 'GET',
    path: '/api/sessions/session_42/reviews',
    query: { filter: 'today & tomorrow', due_only: true },
  })
  assert.equal(
    buildBackendUrl('http://127.0.0.1:8123/', validated),
    'http://127.0.0.1:8123/api/sessions/session_42/reviews?filter=today+%26+tomorrow&due_only=true',
  )
})

test('buildBackendUrl revalidates marked requests after route, query, or body tampering', () => {
  const mutations = [
    (value) => { value.path = '/api/admin' },
    (value) => { value.query = { due_only: ['true'] } },
    (value) => { value.query = { q: 'x'.repeat(65_535) } },
    (value) => { value.body = () => {} },
  ]

  for (const mutate of mutations) {
    const value = expectAccepted({ method: 'POST', path: '/api/chat', body: { message: 'valid' } })
    mutate(value)
    assert.throws(
      () => buildBackendUrl('http://127.0.0.1:8123/', value),
      /validated desktop request/i,
    )
  }
})

test('includes stable desktop error metadata without exposing request payloads', () => {
  assert.deepEqual(
    desktopError('DESKTOP_REQUEST_DENIED', 'Request is not permitted', false, 'request-1'),
    {
      code: 'DESKTOP_REQUEST_DENIED',
      message: 'Request is not permitted',
      retryable: false,
      requestId: 'request-1',
    },
  )
})
