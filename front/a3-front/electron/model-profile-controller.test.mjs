import assert from 'node:assert/strict'
import test from 'node:test'

import { createModelProfileController } from './model-profile-controller.mjs'

const primary = profile('primary')
const backup = profile('backup')
const legacyConfig = {
  provider: 'openai',
  api_key: 'legacy-new-secret-key',
  base_url: 'https://legacy.example.test/v1',
  model_name: 'legacy-new-model',
  anthropic_version: '2023-06-01',
  request_timeout_seconds: 50,
}

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
      id: 'model-a', provider_model_name: `${id}-model`, label: 'Model A',
      max_output_tokens: 4096, supported_reasoning_efforts: ['auto', 'off', 'medium'],
      reasoning_adapter: 'openai_reasoning_effort',
    }],
  }
}

function vaultValue(profiles = [primary]) {
  return {
    version: 2,
    global: { default_profile_id: profiles[0]?.id ?? null, auto_failover: true, fallback_profile_ids: profiles.slice(1).map(value => value.id) },
    profiles,
  }
}

function fakeVault(initial = vaultValue()) {
  let current = structuredClone(initial)
  const calls = []
  return {
    calls,
    async load() { return structuredClone(current) },
    async snapshot() { calls.push('snapshot'); return Buffer.from(JSON.stringify(current)) },
    async save(value) { calls.push('save'); current = structuredClone(value); return structuredClone(current) },
    async restore(bytes) { calls.push('restore'); current = JSON.parse(Buffer.from(bytes).toString('utf8')) },
  }
}

test('bootstrap uses its dedicated startup endpoint before renderer use', async () => {
  const applied = []
  const controller = createModelProfileController({
    validateSender: () => true,
    vault: fakeVault(vaultValue([primary, backup])),
    testProfile: async () => ({ ok: true }),
    bootstrapSnapshot: async value => { applied.push(['bootstrap', value]); return { ready: true } },
    applySnapshot: async value => { applied.push(value); return { ready: true } },
    runtimeStatus: async () => ({ ready: true }),
  })

  const result = await controller.bootstrap()

  assert.equal(result.ready, true)
  assert.equal(applied[0][0], 'bootstrap')
  assert.deepEqual(applied[0][1].fallback_profile_ids, ['backup'])
  assert.equal(applied[0][1].profiles[0].api_key, 'primary-secret-key')
})

test('profile list is redacted and save rollback restores vault and old runtime snapshot', async () => {
  const vault = fakeVault(vaultValue([primary]))
  const applied = []
  const controller = createModelProfileController({
    validateSender: () => true,
    vault,
    testProfile: async () => ({ ok: true, status: 200, data: { status: 'connected' } }),
    applySnapshot: async value => {
      applied.push(value)
      if (value.profiles.some(item => item.id === 'backup')) throw Object.assign(new Error('apply failed backup-secret-key'), { code: 'MODEL_RUNTIME_APPLY_FAILED' })
      return { ready: true }
    },
    runtimeStatus: async () => ({ ready: true }),
  })

  const listed = await controller.list({})
  assert.equal(JSON.stringify(listed).includes('primary-secret-key'), false)
  const result = await controller.upsert({}, backup)

  assert.equal(result.ok, false)
  assert.equal(result.error.code, 'MODEL_RUNTIME_APPLY_FAILED')
  assert.deepEqual(vault.calls, ['snapshot', 'save', 'restore'])
  assert.equal(applied.length, 2)
  assert.deepEqual((await vault.load()).profiles.map(value => value.id), ['primary'])
  assert.doesNotMatch(JSON.stringify(result), /backup-secret-key|apply failed/)
})

test('upsert tests candidate first resolves blank edit keys and never returns secrets', async () => {
  const vault = fakeVault(vaultValue([primary]))
  const tested = []
  const controller = createModelProfileController({
    validateSender: () => true,
    vault,
    testProfile: async value => { tested.push(value); return { ok: true, status: 200, data: { status: 'connected' } } },
    applySnapshot: async () => ({ ready: true }),
    runtimeStatus: async () => ({ ready: true }),
  })
  const result = await controller.upsert({}, { ...primary, label: 'edited', api_key: '' })
  assert.equal(tested[0].api_key, 'primary-secret-key')
  assert.equal(result.ok, true)
  assert.doesNotMatch(JSON.stringify(result), /primary-secret-key/)
})

test('disabling an existing non-default profile does not require a live provider but re-enabling still does', async () => {
  const vault = fakeVault(vaultValue([primary, backup]))
  let testCalls = 0
  const controller = createModelProfileController({
    validateSender: () => true,
    vault,
    testProfile: async () => { testCalls += 1; throw new Error('provider unavailable') },
    applySnapshot: async () => ({ ready: true }),
    runtimeStatus: async () => ({ ready: true }),
  })

  const disabled = await controller.upsert({}, { ...backup, enabled: false, api_key: '' })
  const reenabled = await controller.upsert({}, { ...backup, enabled: true, api_key: '' })

  assert.equal(disabled.ok, true)
  assert.equal((await vault.load()).profiles.find(value => value.id === 'backup').enabled, false)
  assert.equal(testCalls, 1)
  assert.equal(reenabled.error.code, 'MODEL_UNAVAILABLE')
})

test('default deletion last-profile disabling and untrusted senders are rejected', async () => {
  const controller = createModelProfileController({
    validateSender: event => event?.trusted === true,
    vault: fakeVault(vaultValue([primary, backup])),
    testProfile: async () => ({ ok: true }),
    applySnapshot: async () => ({ ready: true }),
    runtimeStatus: async () => ({ ready: true }),
  })
  assert.equal((await controller.delete({ trusted: true }, 'primary')).error.code, 'MODEL_PROFILE_DEFAULT_DELETE_DENIED')
  assert.equal((await controller.upsert({ trusted: false }, backup)).status, 403)

  const single = createModelProfileController({
    validateSender: () => true,
    vault: fakeVault(vaultValue([primary])),
    testProfile: async () => ({ ok: true }),
    applySnapshot: async () => ({ ready: true }),
    runtimeStatus: async () => ({ ready: true }),
  })
  assert.equal((await single.upsert({}, { ...primary, enabled: false })).error.code, 'MODEL_PROFILE_LAST_ENABLED')
})

test('default profile cannot be disabled while another enabled profile exists', async () => {
  const vault = fakeVault(vaultValue([primary, backup]))
  const controller = createModelProfileController({
    validateSender: () => true,
    vault,
    testProfile: async () => ({ ok: true }),
    applySnapshot: async () => ({ ready: true }),
    runtimeStatus: async () => ({ ready: true }),
  })

  const result = await controller.upsert({}, { ...primary, enabled: false })

  assert.equal(result.error.code, 'MODEL_PROFILE_DEFAULT_DISABLE_DENIED')
  assert.deepEqual(vault.calls, [])
})

test('policy rejects missing, duplicate and disabled default profiles before vault writes', async () => {
  const disabled = { ...backup, enabled: false }
  const vault = fakeVault(vaultValue([primary, disabled]))
  const controller = createModelProfileController({
    validateSender: () => true,
    vault,
    testProfile: async () => ({ ok: true }),
    applySnapshot: async () => ({ ready: true }),
    runtimeStatus: async () => ({ ready: true }),
  })

  assert.equal((await controller.savePolicy({}, {
    default_profile_id: 'missing', auto_failover: true, fallback_profile_ids: [],
  })).error.code, 'MODEL_PROFILE_NOT_FOUND')
  assert.equal((await controller.savePolicy({}, {
    default_profile_id: 'backup', auto_failover: true, fallback_profile_ids: ['primary'],
  })).error.code, 'MODEL_PROFILE_DISABLED')
  assert.equal((await controller.savePolicy({}, {
    default_profile_id: 'primary', auto_failover: true, fallback_profile_ids: ['backup', 'backup'],
  })).error.code, 'DESKTOP_REQUEST_INVALID')
  assert.deepEqual(vault.calls, [])
})

test('concurrent profile mutations are serialized so neither update is lost', async () => {
  const vault = fakeVault(vaultValue([primary]))
  const controller = createModelProfileController({
    validateSender: () => true,
    vault,
    testProfile: async () => ({ ok: true }),
    applySnapshot: async () => ({ ready: true }),
    runtimeStatus: async () => ({ ready: true }),
  })

  await Promise.all([
    controller.upsert({}, backup),
    controller.upsert({}, profile('reserve')),
  ])

  assert.deepEqual((await vault.load()).profiles.map(value => value.id).sort(), ['backup', 'primary', 'reserve'])
})

test('rollback leg failure reports recovery required and blocks later mutations', async () => {
  const vault = fakeVault(vaultValue([primary]))
  vault.restore = async () => { throw Object.assign(new Error('restore failed primary-secret-key'), { code: 'RESTORE_FAILED' }) }
  const controller = createModelProfileController({
    validateSender: () => true,
    vault,
    testProfile: async () => ({ ok: true }),
    applySnapshot: async value => {
      if (value.profiles.some(item => item.id === 'backup')) throw new Error('new apply failed')
      return { ready: true }
    },
    runtimeStatus: async () => ({ ready: true }),
  })

  const failed = await controller.upsert({}, backup)
  const blocked = await controller.upsert({}, profile('reserve'))

  assert.equal(failed.error.code, 'MODEL_RUNTIME_ROLLBACK_FAILED')
  assert.equal(blocked.error.code, 'MODEL_RUNTIME_RECOVERY_REQUIRED')
  assert.doesNotMatch(JSON.stringify([failed, blocked]), /primary-secret-key|restore failed/)
})

test('runtime rollback failure is reported even when vault bytes were restored', async () => {
  const vault = fakeVault(vaultValue([primary]))
  let applyCalls = 0
  const controller = createModelProfileController({
    validateSender: () => true,
    vault,
    testProfile: async () => ({ ok: true }),
    applySnapshot: async () => {
      applyCalls += 1
      throw new Error(applyCalls === 1 ? 'new apply failed' : 'old runtime rollback failed primary-secret-key')
    },
    runtimeStatus: async () => ({ ready: true }),
  })

  const result = await controller.upsert({}, backup)

  assert.equal(result.error.code, 'MODEL_RUNTIME_ROLLBACK_FAILED')
  assert.deepEqual((await vault.load()).profiles.map(value => value.id), ['primary'])
  assert.doesNotMatch(JSON.stringify(result), /primary-secret-key|rollback failed/)
})

test('logging failure cannot replace the safe rollback error envelope', async () => {
  const vault = fakeVault(vaultValue([primary]))
  vault.restore = async () => { throw new Error('restore failed') }
  const controller = createModelProfileController({
    validateSender: () => true,
    vault,
    testProfile: async () => ({ ok: true }),
    applySnapshot: async value => {
      if (value.profiles.some(item => item.id === 'backup')) throw new Error('apply failed')
      return { ready: true }
    },
    runtimeStatus: async () => ({ ready: true }),
    log: async () => { throw new Error('log disk unavailable') },
  })

  const result = await controller.upsert({}, backup)

  assert.equal(result.error.code, 'MODEL_RUNTIME_ROLLBACK_FAILED')
})

test('serialized success then failure preserves the first committed profile', async () => {
  const vault = fakeVault(vaultValue([primary]))
  const controller = createModelProfileController({
    validateSender: () => true,
    vault,
    testProfile: async () => ({ ok: true }),
    applySnapshot: async value => {
      if (value.profiles.some(item => item.id === 'reserve')) throw new Error('reserve apply failed')
      return { ready: true }
    },
    runtimeStatus: async () => ({ ready: true }),
  })

  const [first, second] = await Promise.all([
    controller.upsert({}, backup),
    controller.upsert({}, profile('reserve')),
  ])

  assert.equal(first.ok, true)
  assert.equal(second.error.code, 'MODEL_RUNTIME_APPLY_FAILED')
  assert.deepEqual((await vault.load()).profiles.map(value => value.id).sort(), ['backup', 'primary'])
})

test('legacy settings save uses the same mutation queue and returns a redacted compatibility view', async () => {
  const vault = fakeVault(vaultValue([primary]))
  const controller = createModelProfileController({
    validateSender: () => true,
    vault,
    testProfile: async () => ({ ok: true }),
    applySnapshot: async () => ({ ready: true }),
    runtimeStatus: async () => ({ ready: true }),
  })

  const [legacy, added] = await Promise.all([
    controller.upsertLegacy({}, legacyConfig),
    controller.upsert({}, backup),
  ])

  assert.equal(legacy.ok, true)
  assert.equal(legacy.data.model_name, 'legacy-new-model')
  assert.equal(legacy.data.api_key_hint, 'configured')
  assert.equal(added.ok, true)
  assert.deepEqual((await vault.load()).profiles.map(value => value.id).sort(), ['backup', 'primary'])
  assert.doesNotMatch(JSON.stringify(legacy), /legacy-new-secret-key/)
})

test('legacy settings save preserves additional models and default-model capability metadata', async () => {
  const multiModelPrimary = {
    ...primary,
    models: [
      {
        ...primary.models[0],
        label: 'Reasoning Model',
        max_output_tokens: 8192,
        supported_reasoning_efforts: ['auto', 'low', 'high'],
      },
      {
        id: 'model-b', provider_model_name: 'provider-model-b', label: 'Model B',
        max_output_tokens: 2048, supported_reasoning_efforts: ['auto', 'off'],
        reasoning_adapter: 'none',
      },
    ],
  }
  const vault = fakeVault(vaultValue([multiModelPrimary]))
  const controller = createModelProfileController({
    validateSender: () => true,
    vault,
    testProfile: async () => ({ ok: true }),
    applySnapshot: async () => ({ ready: true }),
    runtimeStatus: async () => ({ ready: true }),
  })

  await controller.upsertLegacy({}, legacyConfig)
  const saved = (await vault.load()).profiles[0]

  assert.equal(saved.models.length, 2)
  assert.equal(saved.models[0].provider_model_name, 'legacy-new-model')
  assert.equal(saved.models[0].label, 'Reasoning Model')
  assert.equal(saved.models[0].max_output_tokens, 8192)
  assert.deepEqual(saved.models[0].supported_reasoning_efforts, ['auto', 'low', 'high'])
  assert.deepEqual(saved.models[1], multiModelPrimary.models[1])
})
