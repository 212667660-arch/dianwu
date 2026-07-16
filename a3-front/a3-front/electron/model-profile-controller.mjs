import { desktopError, validateModelConfigInput, validateModelProfilePolicyInput } from './ipc-contract.mjs'

export function createModelProfileController({
  validateSender,
  vault,
  testProfile,
  applySnapshot,
  bootstrapSnapshot = applySnapshot,
  runtimeStatus,
  log = async () => {},
}) {
  if (typeof validateSender !== 'function' || !vault || typeof testProfile !== 'function' || typeof applySnapshot !== 'function' || typeof bootstrapSnapshot !== 'function' || typeof runtimeStatus !== 'function') {
    throw new TypeError('Model profile controller dependencies are required.')
  }
  const trusted = event => trustedResult(validateSender, event)
  let mutationTail = Promise.resolve()
  let recoveryRequired = false

  return {
    bootstrap,
    list,
    test,
    testLegacy,
    upsert: (event, input) => mutate(() => upsert(event, input)),
    upsertLegacy: (event, input) => mutate(() => upsertLegacy(event, input)),
    delete: (event, profileId) => mutate(() => remove(event, profileId)),
    savePolicy: (event, policy) => mutate(() => savePolicy(event, policy)),
    status,
  }

  function mutate(operation) {
    const guarded = () => recoveryRequired
      ? failure('MODEL_RUNTIME_RECOVERY_REQUIRED', '模型配置恢复未完成，请重启应用后再试。', 503)
      : operation()
    const result = mutationTail.then(guarded, guarded)
    mutationTail = result.then(() => undefined, () => undefined)
    return result
  }

  async function bootstrap() {
    const result = await bootstrapSnapshot(toRuntimeSnapshot(await vault.load()))
    recoveryRequired = false
    return result
  }

  async function list(event) {
    if (!trusted(event)) return denied()
    return success(redactVault(await vault.load()))
  }

  async function status(event) {
    if (!trusted(event)) return denied()
    try { return success(await runtimeStatus()) } catch { return failure('MODEL_UNAVAILABLE', '模型运行状态暂时不可用。', 503, true) }
  }

  async function test(event, input) {
    if (!trusted(event)) return denied()
    const current = await vault.load()
    const candidate = resolveKey(input, current)
    if (!candidate) return failure('MODEL_API_KEY_REQUIRED', '首次配置模型时必须输入 API Key。', 400)
    try { return await testProfile(candidate) } catch { return failure('MODEL_UNAVAILABLE', '模型服务暂时不可用，请稍后重试。', 503, true) }
  }

  async function testLegacy(event, input) {
    if (!trusted(event)) return denied()
    const validation = validateModelConfigInput(input)
    if (!validation.ok) return { ok: false, status: 400, error: validation.error }
    return test(event, legacyProfile(validation.value, await vault.load()))
  }

  async function upsert(event, input) {
    if (!trusted(event)) return denied()
    const current = await vault.load()
    const candidate = resolveKey(input, current)
    if (!candidate) return failure('MODEL_API_KEY_REQUIRED', '首次配置模型时必须输入 API Key。', 400)
    const profiles = current.profiles.filter(value => value.id !== candidate.id)
    profiles.push(candidate)
    if (!profiles.some(value => value.enabled)) return failure('MODEL_PROFILE_LAST_ENABLED', '至少需要保留一个启用的模型配置。', 409)
    if (candidate.id === current.global.default_profile_id && !candidate.enabled) return failure('MODEL_PROFILE_DEFAULT_DISABLE_DENIED', '请先选择新的默认模型配置，再停用当前默认配置。', 409)
    const tested = await test(event, candidate)
    if (!tested?.ok) return tested
    const next = {
      ...current,
      global: {
        ...current.global,
        default_profile_id: current.global.default_profile_id ?? candidate.id,
      },
      profiles,
    }
    return commit(next)
  }

  async function upsertLegacy(event, input) {
    if (!trusted(event)) return denied()
    const validation = validateModelConfigInput(input)
    if (!validation.ok) return { ok: false, status: 400, error: validation.error }
    const profile = legacyProfile(validation.value, await vault.load())
    const result = await upsert(event, profile)
    return result.ok ? success(legacySettings(profile)) : result
  }

  async function remove(event, profileId) {
    if (!trusted(event)) return denied()
    const current = await vault.load()
    if (current.global.default_profile_id === profileId) return failure('MODEL_PROFILE_DEFAULT_DELETE_DENIED', '默认模型配置不能直接删除。', 409)
    if (!current.profiles.some(value => value.id === profileId)) return failure('MODEL_PROFILE_NOT_FOUND', '指定的模型配置不存在。', 404)
    const profiles = current.profiles.filter(value => value.id !== profileId)
    if (!profiles.some(value => value.enabled)) return failure('MODEL_PROFILE_LAST_ENABLED', '至少需要保留一个启用的模型配置。', 409)
    return commit({
      ...current,
      global: {
        ...current.global,
        fallback_profile_ids: current.global.fallback_profile_ids.filter(value => value !== profileId),
      },
      profiles,
    })
  }

  async function savePolicy(event, policy) {
    if (!trusted(event)) return denied()
    const current = await vault.load()
    const validation = validateModelProfilePolicyInput(policy)
    if (!validation.ok) return { ok: false, status: 400, error: validation.error }
    const value = validation.value
    if (current.profiles.length && value.default_profile_id === null) return failure('DESKTOP_REQUEST_INVALID', '默认模型配置不能为空。', 400)
    const profiles = new Map(current.profiles.map(profile => [profile.id, profile]))
    if (value.default_profile_id !== null && !profiles.has(value.default_profile_id)) return failure('MODEL_PROFILE_NOT_FOUND', '指定的模型配置不存在。', 404)
    if (value.default_profile_id !== null && !profiles.get(value.default_profile_id).enabled) return failure('MODEL_PROFILE_DISABLED', '默认模型配置必须处于启用状态。', 409)
    if (value.fallback_profile_ids.some(id => !profiles.has(id))) return failure('MODEL_PROFILE_NOT_FOUND', '备用模型配置不存在。', 404)
    return commit({ ...current, global: value })
  }

  async function commit(next) {
    const previous = await vault.load()
    const bytes = await vault.snapshot()
    let saved
    try { saved = await vault.save(next) } catch (error) { return credentialFailure(error) }
    try {
      const status = await applySnapshot(toRuntimeSnapshot(saved))
      return success({ vault: redactVault(saved), runtime: status })
    } catch (error) {
      let rollbackFailed = false
      try { await vault.restore(bytes) } catch (restoreError) {
        rollbackFailed = true
        await safeLog(log, { event: 'model_profile_restore_failed', code: safeCode(restoreError) })
      }
      try { await applySnapshot(toRuntimeSnapshot(previous)) } catch (rollbackError) {
        rollbackFailed = true
        await safeLog(log, { event: 'model_runtime_rollback_failed', code: safeCode(rollbackError) })
      }
      if (rollbackFailed) {
        recoveryRequired = true
        return failure('MODEL_RUNTIME_ROLLBACK_FAILED', '模型配置恢复未完成，请重启应用。', 503)
      }
      return failure('MODEL_RUNTIME_APPLY_FAILED', '新模型配置未能启用，已恢复原配置。', 503)
    }
  }
}

export function toRuntimeSnapshot(vault) {
  return {
    default_profile_id: vault.global.default_profile_id,
    auto_failover: vault.global.auto_failover,
    fallback_profile_ids: [...vault.global.fallback_profile_ids],
    profiles: vault.profiles.map(value => structuredClone(value)),
  }
}

function resolveKey(input, vault) {
  if (!input || typeof input !== 'object' || Array.isArray(input)) return null
  const existing = vault.profiles.find(value => value.id === input.id)
  const apiKey = typeof input.api_key === 'string' && input.api_key ? input.api_key : existing?.api_key
  return apiKey ? { ...structuredClone(input), api_key: apiKey } : null
}

function redactVault(vault) {
  return {
    version: vault.version,
    global: structuredClone(vault.global),
    profiles: vault.profiles.map(({ api_key, ...value }) => ({ ...structuredClone(value), api_key_configured: Boolean(api_key) })),
  }
}

function legacyProfile(input, vault) {
  const profileId = vault.global.default_profile_id ?? 'legacy-profile'
  const existing = vault.profiles.find(profile => profile.id === profileId)
  const modelId = existing?.default_model_id ?? 'legacy-model'
  const models = existing
    ? existing.models.map(model => model.id === modelId
      ? { ...structuredClone(model), provider_model_name: input.model_name }
      : structuredClone(model))
    : [{
        id: modelId,
        provider_model_name: input.model_name,
        label: input.model_name,
        max_output_tokens: 4096,
        supported_reasoning_efforts: ['auto', 'off'],
        reasoning_adapter: 'none',
      }]
  return {
    id: profileId,
    label: existing?.label ?? '原模型配置',
    enabled: true,
    provider: input.provider,
    base_url: input.base_url,
    api_key: input.api_key,
    anthropic_version: input.anthropic_version,
    request_timeout_seconds: input.request_timeout_seconds,
    default_model_id: modelId,
    models,
  }
}

function legacySettings(profile) {
  const model = profile.models.find(value => value.id === profile.default_model_id)
  return {
    provider: profile.provider,
    base_url: profile.base_url,
    model_name: model.provider_model_name,
    api_key_configured: true,
    api_key_hint: 'configured',
    anthropic_version: profile.anthropic_version,
    request_timeout_seconds: profile.request_timeout_seconds,
  }
}

function trustedResult(validateSender, event) {
  try { return validateSender(event) === true } catch { return false }
}
function denied() { return failure('DESKTOP_REQUEST_DENIED', '模型配置请求未获授权。', 403) }
function success(data) { return { ok: true, status: 200, data } }
function failure(code, message, status, retryable = false) { return { ok: false, status, error: desktopError(code, message, retryable) } }
function safeCode(error) { return typeof error?.code === 'string' ? error.code : 'MODEL_PROFILE_OPERATION_FAILED' }
async function safeLog(log, entry) { try { await log(entry) } catch {} }
function credentialFailure(error) { return failure(error?.code === 'MODEL_CREDENTIAL_STORE_UNAVAILABLE' ? error.code : 'MODEL_CREDENTIAL_STORE_INVALID', '模型凭据存储不可用，请检查应用数据目录。', 503) }
