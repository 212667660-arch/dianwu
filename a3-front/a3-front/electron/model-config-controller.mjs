import { desktopError, validateModelConfigInput } from './ipc-contract.mjs'

export function createBackendModelTester({ getRuntime, fetchImpl = fetch }) {
  if (typeof getRuntime !== 'function' || typeof fetchImpl !== 'function') {
    throw new TypeError('Backend model tester dependencies are required.')
  }

  return async function testBackendModel(input) {
    const runtime = getRuntime()
    if (!runtime?.baseUrl || !runtime?.token) return unavailableResponse()

    let response
    try {
      response = await fetchImpl(new URL('/api/settings/model/test', `${runtime.baseUrl}/`).toString(), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-A3-Desktop-Token': runtime.token,
        },
        body: JSON.stringify(input),
      })
    } catch {
      return unavailableResponse()
    }

    const status = Number.isInteger(response?.status) ? response.status : 503
    let body
    try {
      body = await response.json()
    } catch {
      body = null
    }
    if (status >= 200 && status < 300 && body && typeof body === 'object' && !Array.isArray(body)) {
      return { ok: true, status, data: body }
    }
    if (body && typeof body.code === 'string' && typeof body.message === 'string') {
      return {
        ok: false,
        status,
        error: desktopError(
          body.code,
          body.message,
          body.retryable === true,
          typeof body.request_id === 'string' ? body.request_id : undefined,
        ),
      }
    }
    return unavailableResponse(status)
  }
}

export function createModelConfigController({
  validateSender,
  configStore,
  testCandidate,
  restart,
  getCurrentSettings,
  log = async () => {},
}) {
  if (
    typeof validateSender !== 'function'
    || !configStore
    || typeof testCandidate !== 'function'
    || typeof restart !== 'function'
    || typeof getCurrentSettings !== 'function'
  ) {
    throw new TypeError('Model config controller dependencies are required.')
  }

  return { test, save }

  async function test(event, input) {
    const validation = authorizeAndValidate(event, input)
    if (!validation.ok) return validation.response
    const candidate = await resolveCredential(validation.value)
    if (!candidate.ok) return candidate.response
    try {
      return await testCandidate(candidate.value)
    } catch {
      return unavailableResponse()
    }
  }

  async function save(event, input) {
    const validation = authorizeAndValidate(event, input)
    if (!validation.ok) return validation.response
    const candidate = await resolveCredential(validation.value)
    if (!candidate.ok) return candidate.response

    let tested
    try {
      tested = await testCandidate(candidate.value)
    } catch {
      return unavailableResponse()
    }
    if (!tested?.ok) return tested

    let previousConfig
    let snapshot
    try {
      previousConfig = await configStore.load()
      snapshot = await configStore.snapshot()
      await configStore.save(candidate.value)
    } catch (error) {
      return credentialStoreFailure(error)
    }
    try {
      await restart(candidate.value)
      const settings = await getCurrentSettings()
      return { ok: true, status: 200, data: settings }
    } catch (error) {
      await configStore.restore(snapshot).catch(async restoreError => {
        await log({ event: 'model_config_restore_failed', code: safeCode(restoreError) })
      })
      try {
        await restart(previousConfig)
      } catch (rollbackError) {
        await log({ event: 'model_config_rollback_restart_failed', code: safeCode(rollbackError) })
      }
      return {
        ok: false,
        status: 503,
        error: desktopError(
          'MODEL_RESTART_FAILED',
          '新模型配置未能启用，已恢复原配置。',
          true,
        ),
      }
    }
  }

  function authorizeAndValidate(event, input) {
    let trusted = false
    try {
      trusted = validateSender(event) === true
    } catch {
      trusted = false
    }
    if (!trusted) {
      return {
        ok: false,
        response: {
          ok: false,
          status: 403,
          error: desktopError('DESKTOP_REQUEST_DENIED', '模型配置请求未获授权。'),
        },
      }
    }
    const validation = validateModelConfigInput(input)
    if (!validation.ok) {
      return { ok: false, response: { ok: false, status: 400, error: validation.error } }
    }
    return { ok: true, value: validation.value }
  }

  async function resolveCredential(value) {
    if (value.api_key) return { ok: true, value }
    let current
    try {
      current = await configStore.load()
    } catch (error) {
      return { ok: false, response: credentialStoreFailure(error) }
    }
    if (typeof current?.api_key === 'string' && current.api_key) {
      return { ok: true, value: { ...value, api_key: current.api_key } }
    }
    return {
      ok: false,
      response: {
        ok: false,
        status: 400,
        error: desktopError(
          'MODEL_API_KEY_REQUIRED',
          '首次配置模型时必须输入 API Key。',
        ),
      },
    }
  }
}

function unavailableResponse(status = 503) {
  return {
    ok: false,
    status,
    error: desktopError('MODEL_UNAVAILABLE', '模型服务暂时不可用，请稍后重试。', true),
  }
}

function safeCode(error) {
  return typeof error?.code === 'string' ? error.code : 'MODEL_CONFIG_OPERATION_FAILED'
}

function credentialStoreFailure(error) {
  const code = error?.code === 'MODEL_CREDENTIAL_STORE_UNAVAILABLE'
    ? 'MODEL_CREDENTIAL_STORE_UNAVAILABLE'
    : 'MODEL_CREDENTIAL_STORE_INVALID'
  return {
    ok: false,
    status: 503,
    error: desktopError(
      code,
      code === 'MODEL_CREDENTIAL_STORE_UNAVAILABLE'
        ? '当前系统无法安全保存模型凭据。'
        : '模型凭据存储不可用，请检查应用数据目录。',
      false,
    ),
  }
}
