import assert from 'node:assert/strict'
import { mkdtemp, readFile, rm } from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import test from 'node:test'

import { createModelConfigStore } from './model-config.mjs'
import { createModelProfileVault } from './model-profile-vault.mjs'

const legacyConfig = {
  provider: 'openai',
  api_key: 'test-secret-key',
  base_url: 'https://api.example.test/v1',
  model_name: 'legacy-model-name',
  anthropic_version: '2023-06-01',
  request_timeout_seconds: 60,
}

function safeStorage() {
  return {
    isEncryptionAvailable: () => true,
    encryptString: value => Buffer.from(`cipher:${value}`, 'utf8'),
    decryptString: value => Buffer.from(value).toString('utf8').slice('cipher:'.length),
  }
}

async function fixture(callback) {
  const directory = await mkdtemp(path.join(os.tmpdir(), 'a3-model-profiles-'))
  try {
    const storage = safeStorage()
    const legacyStore = createModelConfigStore({
      safeStorage: storage,
      filePath: path.join(directory, 'model-settings.enc'),
    })
    const filePath = path.join(directory, 'model-profiles.enc')
    const vault = createModelProfileVault({ safeStorage: storage, filePath, legacyStore })
    return await callback({ vault, legacyStore, filePath })
  } finally {
    await rm(directory, { recursive: true, force: true })
  }
}

test('empty installation returns a valid version two vault', async () => {
  await fixture(async ({ vault }) => {
    assert.deepEqual(await vault.load(), {
      version: 2,
      global: { default_profile_id: null, auto_failover: true, fallback_profile_ids: [] },
      profiles: [],
    })
  })
})

test('version one config migrates in memory without exposing or rewriting its key', async () => {
  await fixture(async ({ vault, legacyStore, filePath }) => {
    await legacyStore.save(legacyConfig)
    const migrated = await vault.load()
    assert.equal(migrated.version, 2)
    assert.equal(migrated.profiles.length, 1)
    assert.equal(migrated.profiles[0].api_key, 'test-secret-key')
    assert.equal(migrated.profiles[0].models[0].provider_model_name, 'legacy-model-name')
    assert.equal(migrated.global.default_profile_id, migrated.profiles[0].id)
    await assert.rejects(readFile(filePath))
  })
})

test('multi-profile save is encrypted and round trips with first profile as default', async () => {
  await fixture(async ({ vault, filePath }) => {
    const value = await vault.save({
      version: 2,
      global: { default_profile_id: null, auto_failover: true, fallback_profile_ids: [] },
      profiles: [profile('primary'), profile('backup'), profile('third')],
    })
    assert.equal(value.global.default_profile_id, 'primary')
    assert.deepEqual(await vault.load(), value)
    assert.doesNotMatch((await readFile(filePath)).toString('utf8'), /primary-secret-key|backup-secret-key/)
  })
})

test('duplicate ids unknown fields and corrupt envelopes are rejected safely', async () => {
  await fixture(async ({ vault, filePath }) => {
    await assert.rejects(
      () => vault.save({
        version: 2,
        global: { default_profile_id: 'primary', auto_failover: true, fallback_profile_ids: [] },
        profiles: [profile('primary'), profile('primary')],
      }),
      error => error?.code === 'MODEL_CREDENTIAL_STORE_INVALID',
    )
    await assert.rejects(
      () => vault.save({
        version: 2,
        global: { default_profile_id: null, auto_failover: true, fallback_profile_ids: [] },
        profiles: [],
        arbitrary: true,
      }),
      error => error?.code === 'MODEL_CREDENTIAL_STORE_INVALID',
    )
    await import('node:fs/promises').then(fs => fs.writeFile(filePath, '{"version":2,"payload":"%%%"}'))
    await assert.rejects(() => vault.load(), error => error?.code === 'MODEL_CREDENTIAL_STORE_INVALID')
  })
})

function profile(id) {
  return {
    id,
    label: id,
    enabled: true,
    provider: 'openai',
    base_url: `https://${id}.example.test/v1`,
    api_key: `${id}-secret-key`,
    anthropic_version: '2023-06-01',
    request_timeout_seconds: 60,
    default_model_id: 'model-a',
    models: [{
      id: 'model-a',
      provider_model_name: `${id}-model`,
      label: 'Model A',
      max_output_tokens: 4096,
      supported_reasoning_efforts: ['auto', 'off', 'medium'],
      reasoning_adapter: 'openai_reasoning_effort',
    }],
  }
}
