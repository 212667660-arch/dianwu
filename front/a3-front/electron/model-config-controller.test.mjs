import assert from 'node:assert/strict'
import test from 'node:test'

import { createBackendModelTester, createModelConfigController } from './model-config-controller.mjs'

const oldConfig = {
  provider: 'openai',
  api_key: 'old-secret-key',
  base_url: 'https://api.example.test',
  model_name: 'old-model',
  anthropic_version: '2023-06-01',
  request_timeout_seconds: 60,
}

const newConfig = { ...oldConfig, api_key: 'new-secret-key', model_name: 'new-model' }

function connectedResult() {
  return {
    ok: true,
    status: 200,
    data: { provider: 'openai', model_name: 'new-model', status: 'connected', latency_ms: 12 },
  }
}

function fakeStore(initial = oldConfig) {
  let current = initial
  let snapshot = initial
  const calls = []
  return {
    calls,
    async load() { return current },
    async snapshot() { calls.push('snapshot'); snapshot = current; return snapshot },
    async save(value) { calls.push('save'); current = value; return value },
    async restore(value) { calls.push('restore'); current = value },
  }
}

test('测试失败时保存控制器不写入配置且不重启后端', async () => {
  const store = fakeStore()
  let restartCalls = 0
  const controller = createModelConfigController({
    validateSender: () => true,
    testCandidate: async () => ({
      ok: false,
      status: 401,
      error: { code: 'MODEL_AUTHENTICATION_ERROR', message: '认证失败。', retryable: false },
    }),
    configStore: store,
    restart: async () => { restartCalls += 1 },
    getCurrentSettings: async () => ({ api_key_configured: true }),
  })

  const result = await controller.save({}, newConfig)

  assert.equal(result.ok, false)
  assert.equal(result.error.code, 'MODEL_AUTHENTICATION_ERROR')
  assert.deepEqual(store.calls, [])
  assert.equal(restartCalls, 0)
})

test('新后端 ready 失败时恢复旧配置并重启旧后端', async () => {
  const store = fakeStore()
  const restartedWith = []
  const controller = createModelConfigController({
    validateSender: () => true,
    testCandidate: async () => connectedResult(),
    configStore: store,
    restart: async value => {
      restartedWith.push(value)
      if (value?.model_name === 'new-model') throw new Error('ready timeout')
    },
    getCurrentSettings: async () => ({ api_key_configured: true }),
  })

  const result = await controller.save({}, newConfig)

  assert.equal(result.ok, false)
  assert.equal(result.error.code, 'MODEL_RESTART_FAILED')
  assert.deepEqual(await store.load(), oldConfig)
  assert.deepEqual(restartedWith, [newConfig, oldConfig])
  assert.deepEqual(store.calls, ['snapshot', 'save', 'restore'])
})

test('受信 sender 测试成功后保存并只返回脱敏设置', async () => {
  const store = fakeStore()
  const settings = {
    provider: 'openai',
    base_url: newConfig.base_url,
    model_name: newConfig.model_name,
    api_key_configured: true,
    api_key_hint: 'new-...-key',
    anthropic_version: newConfig.anthropic_version,
    request_timeout_seconds: 60,
  }
  const controller = createModelConfigController({
    validateSender: () => true,
    testCandidate: async () => connectedResult(),
    configStore: store,
    restart: async () => {},
    getCurrentSettings: async () => settings,
  })

  const result = await controller.save({}, newConfig)

  assert.deepEqual(result, { ok: true, status: 200, data: settings })
  assert.doesNotMatch(JSON.stringify(result), /new-secret-key/)
})

test('外部 sender 不能测试或保存候选配置', async () => {
  const controller = createModelConfigController({
    validateSender: () => false,
    testCandidate: async () => connectedResult(),
    configStore: fakeStore(),
    restart: async () => {},
    getCurrentSettings: async () => ({}),
  })

  for (const result of [await controller.test({}, newConfig), await controller.save({}, newConfig)]) {
    assert.equal(result.ok, false)
    assert.equal(result.status, 403)
    assert.equal(result.error.code, 'DESKTOP_REQUEST_DENIED')
  }
})

test('模型连接测试只请求固定后端路径并由主进程注入令牌', async () => {
  const calls = []
  const tester = createBackendModelTester({
    getRuntime: () => ({ baseUrl: 'http://127.0.0.1:8123', token: 'desktop-token' }),
    fetchImpl: async (url, options) => {
      calls.push({ url, options })
      return new Response(JSON.stringify(connectedResult().data), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    },
  })

  const result = await tester(newConfig)

  assert.deepEqual(result, connectedResult())
  assert.equal(calls[0].url, 'http://127.0.0.1:8123/api/settings/model/test')
  assert.equal(calls[0].options.method, 'POST')
  assert.equal(calls[0].options.headers['X-A3-Desktop-Token'], 'desktop-token')
  assert.deepEqual(JSON.parse(calls[0].options.body), newConfig)
})

test('模型连接测试保留结构化后端错误且网络失败不泄露候选配置', async () => {
  const structured = createBackendModelTester({
    getRuntime: () => ({ baseUrl: 'http://127.0.0.1:8123', token: 'desktop-token' }),
    fetchImpl: async () => new Response(JSON.stringify({
      code: 'MODEL_AUTHENTICATION_ERROR',
      message: '认证失败。',
      retryable: false,
      request_id: 'req-1',
    }), { status: 401, headers: { 'content-type': 'application/json' } }),
  })
  assert.deepEqual(await structured(newConfig), {
    ok: false,
    status: 401,
    error: {
      code: 'MODEL_AUTHENTICATION_ERROR',
      message: '认证失败。',
      retryable: false,
      requestId: 'req-1',
    },
  })

  const unavailable = createBackendModelTester({
    getRuntime: () => ({ baseUrl: 'http://127.0.0.1:8123', token: 'desktop-token' }),
    fetchImpl: async () => { throw new Error(`failed ${newConfig.api_key}`) },
  })
  const result = await unavailable(newConfig)
  assert.equal(result.error.code, 'MODEL_UNAVAILABLE')
  assert.doesNotMatch(JSON.stringify(result), /new-secret-key/)
})

test('已有配置允许空 Key 沿用旧凭据，首次配置仍要求 Key', async () => {
  const tested = []
  const store = fakeStore(oldConfig)
  const controller = createModelConfigController({
    validateSender: () => true,
    testCandidate: async value => { tested.push(value); return connectedResult() },
    configStore: store,
    restart: async () => {},
    getCurrentSettings: async () => ({ api_key_configured: true }),
  })
  const result = await controller.test({}, { ...newConfig, api_key: '' })

  assert.equal(result.ok, true)
  assert.equal(tested[0].api_key, oldConfig.api_key)
  const saved = await controller.save({}, { ...newConfig, api_key: '' })
  assert.equal(saved.ok, true)
  assert.equal((await store.load()).api_key, oldConfig.api_key)

  const firstRun = createModelConfigController({
    validateSender: () => true,
    testCandidate: async () => connectedResult(),
    configStore: fakeStore(null),
    restart: async () => {},
    getCurrentSettings: async () => ({}),
  })
  const missing = await firstRun.test({}, { ...newConfig, api_key: '' })
  assert.equal(missing.error.code, 'MODEL_API_KEY_REQUIRED')
})

test('安全存储写入失败时保留运行中的旧后端且不伪装成重启失败', async () => {
  let restartCalls = 0
  const controller = createModelConfigController({
    validateSender: () => true,
    testCandidate: async () => connectedResult(),
    configStore: {
      async load() { return oldConfig },
      async snapshot() { return Buffer.from('old') },
      async save() {
        throw Object.assign(new Error('safe storage unavailable'), {
          code: 'MODEL_CREDENTIAL_STORE_UNAVAILABLE',
        })
      },
      async restore() { throw new Error('restore must not run') },
    },
    restart: async () => { restartCalls += 1 },
    getCurrentSettings: async () => ({}),
  })

  const result = await controller.save({}, newConfig)

  assert.equal(result.error.code, 'MODEL_CREDENTIAL_STORE_UNAVAILABLE')
  assert.equal(restartCalls, 0)
})

test('empty API key returns a structured error when the stored credential is invalid', async () => {
  const controller = createModelConfigController({
    validateSender: () => true,
    testCandidate: async () => connectedResult(),
    configStore: {
      async load() {
        throw Object.assign(new Error('invalid encrypted payload'), {
          code: 'MODEL_CREDENTIAL_STORE_INVALID',
        })
      },
      async snapshot() { throw new Error('snapshot must not run') },
      async save() { throw new Error('save must not run') },
      async restore() { throw new Error('restore must not run') },
    },
    restart: async () => { throw new Error('restart must not run') },
    getCurrentSettings: async () => ({}),
  })

  const result = await controller.test({}, { ...newConfig, api_key: '' })

  assert.equal(result.ok, false)
  assert.equal(result.status, 503)
  assert.equal(result.error.code, 'MODEL_CREDENTIAL_STORE_INVALID')
  assert.doesNotMatch(JSON.stringify(result), /invalid encrypted payload/)
})
