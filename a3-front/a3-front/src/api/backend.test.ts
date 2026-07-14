import { beforeEach, describe, expect, it, vi } from 'vitest'
import { backendApi, parseSseBlock, readSseBody } from './backend'

const modelInput = {
  provider: 'openai' as const,
  api_key: 'test-secret-key',
  base_url: 'https://api.example.test',
  model_name: 'test-model',
  anthropic_version: '2023-06-01',
  request_timeout_seconds: 60,
}

beforeEach(() => {
  delete window.a3Desktop
})

function streamFrom(chunks: string[]) {
  const encoder = new TextEncoder()
  return new ReadableStream<Uint8Array>({
    start(controller) {
      chunks.forEach(chunk => controller.enqueue(encoder.encode(chunk)))
      controller.close()
    },
  })
}

describe('SSE response parsing', () => {
  it('preserves events split across network chunks', async () => {
    const events: Array<{ event: string; content?: string; state?: string }> = []
    await readSseBody(streamFrom([
      'event: delta\ndata: {"content":"你',
      '好"}\n\nevent: done\ndata: {"state":"DIAGNOSING"}\n\n',
    ]), event => events.push(event))

    expect(events).toEqual([
      { event: 'delta', content: '你好' },
      { event: 'done', state: 'DIAGNOSING' },
    ])
  })

  it('rejects malformed event payloads with a user-safe message', () => {
    expect(() => parseSseBlock('event: delta\ndata: {not-json}')).toThrow('流式响应数据格式错误')
  })
})

describe('model settings API', () => {
  it('uses fixed desktop bridge methods for testing and saving model settings', async () => {
    const modelConfigTest = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      data: { provider: 'openai', model_name: 'test-model', status: 'connected', latency_ms: 12 },
    })
    const savedSettings = {
      provider: 'openai',
      base_url: modelInput.base_url,
      model_name: modelInput.model_name,
      api_key_configured: true,
      api_key_hint: 'test...-key',
      anthropic_version: modelInput.anthropic_version,
      request_timeout_seconds: 60,
    }
    const modelConfigSave = vi.fn().mockResolvedValue({ ok: true, status: 200, data: savedSettings })
    const request = vi.fn()
    window.a3Desktop = {
      request,
      modelConfigTest,
      modelConfigSave,
      startStream: vi.fn(),
      cancelStream: vi.fn(),
      onStreamEvent: vi.fn(() => () => {}),
      onBackendExit: vi.fn(() => () => {}),
    }

    await expect(backendApi.testModelSettings(modelInput)).resolves.toEqual({
      provider: 'openai', model_name: 'test-model', status: 'connected', latency_ms: 12,
    })
    await expect(backendApi.saveModelSettings(modelInput)).resolves.toEqual(savedSettings)

    expect(modelConfigTest).toHaveBeenCalledWith(modelInput)
    expect(modelConfigSave).toHaveBeenCalledWith(modelInput)
    expect(request).not.toHaveBeenCalled()
  })

  it('converts a fixed desktop model config error to DesktopApiError', async () => {
    window.a3Desktop = {
      request: vi.fn(),
      modelConfigTest: vi.fn().mockResolvedValue({
        ok: false,
        status: 401,
        error: { code: 'MODEL_AUTHENTICATION_ERROR', message: '认证失败。', retryable: false },
      }),
      modelConfigSave: vi.fn(),
      startStream: vi.fn(),
      cancelStream: vi.fn(),
      onStreamEvent: vi.fn(() => () => {}),
      onBackendExit: vi.fn(() => () => {}),
    }

    await expect(backendApi.testModelSettings(modelInput)).rejects.toMatchObject({
      name: 'DesktopApiError',
      code: 'MODEL_AUTHENTICATION_ERROR',
      status: 401,
    })
  })
})
