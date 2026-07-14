import assert from 'node:assert/strict'
import { mkdtemp, readFile, rm } from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import test from 'node:test'

import { createModelConfigStore, modelEnvironment } from './model-config.mjs'

const baseConfig = {
  provider: 'openai',
  api_key: 'test-secret-key',
  base_url: 'https://api.example.test',
  model_name: 'test-model',
  anthropic_version: '2023-06-01',
  request_timeout_seconds: 60,
}

function fakeSafeStorage(available = true) {
  return {
    isEncryptionAvailable: () => available,
    encryptString: value => Buffer.from(`cipher:${value}`, 'utf8'),
    decryptString: value => Buffer.from(value).toString('utf8').slice('cipher:'.length),
  }
}

async function withStore(safeStorage, callback) {
  const directory = await mkdtemp(path.join(os.tmpdir(), 'a3-model-config-'))
  const filePath = path.join(directory, 'model-settings.enc')
  try {
    return await callback(createModelConfigStore({ safeStorage, filePath }), filePath)
  } finally {
    await rm(directory, { recursive: true, force: true })
  }
}

test('保存配置只写入密文并可读取同一配置', async () => {
  await withStore(fakeSafeStorage(), async (store, filePath) => {
    await store.save(baseConfig)

    const bytes = await readFile(filePath)
    assert.doesNotMatch(bytes.toString('utf8'), /test-secret-key/)
    assert.deepEqual(await store.load(), baseConfig)
    assert.deepEqual(modelEnvironment(baseConfig), {
      MODEL_PROVIDER: 'openai',
      MODEL_API_KEY: 'test-secret-key',
      MODEL_BASE_URL: 'https://api.example.test',
      MODEL_NAME: 'test-model',
      ANTHROPIC_VERSION: '2023-06-01',
      REQUEST_TIMEOUT_SECONDS: '60',
    })
  })
})

test('safeStorage 不可用时拒绝保存且不创建明文文件', async () => {
  await withStore(fakeSafeStorage(false), async (store, filePath) => {
    await assert.rejects(
      () => store.save(baseConfig),
      error => error?.code === 'MODEL_CREDENTIAL_STORE_UNAVAILABLE',
    )
    await assert.rejects(readFile(filePath))
  })
})

test('原子替换前的旧密文可以恢复', async () => {
  await withStore(fakeSafeStorage(), async store => {
    const oldConfig = { ...baseConfig, model_name: 'old-model' }
    const newConfig = { ...baseConfig, model_name: 'new-model' }
    await store.save(oldConfig)
    const snapshot = await store.snapshot()
    await store.save(newConfig)
    await store.restore(snapshot)

    assert.deepEqual(await store.load(), oldConfig)
  })
})
