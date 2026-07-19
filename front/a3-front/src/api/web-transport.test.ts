import { describe, expect, it, vi } from 'vitest'

import { BackendApiError, backendApiErrorFromEnvelope } from './transport'
import { errorMessage } from './client'
import { createWebTransport } from './web-transport'

const missingSession = {
  code: 'SESSION_NOT_FOUND',
  message: '会话不存在。',
  retryable: false,
  request_id: 'req-web-404',
}

describe('Web transport error contract', () => {
  it('converts a canonical ordinary Web 404 response to BackendApiError', async () => {
    const httpClient = {
      request: vi.fn().mockResolvedValue({ status: 404, data: missingSession }),
    }
    const transport = createWebTransport({ httpClient })

    await expect(transport.request({ method: 'GET', path: '/api/sessions/missing' })).rejects.toMatchObject({
      name: 'BackendApiError',
      status: 404,
      code: 'SESSION_NOT_FOUND',
      message: '会话不存在。',
      retryable: false,
      requestId: 'req-web-404',
    })
  })

  it('converts a canonical SSE setup failure to BackendApiError', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      code: 'MODEL_NOT_READY',
      message: '模型服务尚未配置。',
      retryable: false,
      request_id: 'req-web-503',
    }), { status: 503, headers: { 'Content-Type': 'application/json' } }))
    const transport = createWebTransport({ fetchImpl })

    await expect(transport.stream(
      { method: 'POST', path: '/api/chat/stream', body: { session_id: 'student_1', message: '你好' } },
      () => {},
    )).rejects.toMatchObject({
      name: 'BackendApiError',
      status: 503,
      code: 'MODEL_NOT_READY',
      requestId: 'req-web-503',
    })
  })

  it('uses a safe generic error for malformed upstream bodies and unknown errors', () => {
    const malformed = backendApiErrorFromEnvelope(502, { detail: 'private upstream details' })

    expect(malformed).toMatchObject({
      name: 'BackendApiError',
      status: 502,
      code: 'BACKEND_HTTP_ERROR',
      retryable: true,
    })
    expect(malformed.message).not.toContain('private upstream')
    expect(errorMessage(new Error('private transport details'))).toBe('请求失败，请稍后重试。')
  })

  it('exposes the canonical error as a real BackendApiError instance', () => {
    const error = backendApiErrorFromEnvelope(404, missingSession)
    expect(error).toBeInstanceOf(BackendApiError)
  })
})
