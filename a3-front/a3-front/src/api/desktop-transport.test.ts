import { describe, expect, it, vi } from 'vitest'

import { createDesktopTransport } from './desktop-transport'
import { DesktopApiError, type DesktopBridge, type DesktopStreamMessage } from './transport'

function fakeBridge() {
  let listener: ((message: DesktopStreamMessage) => void) | undefined
  const unsubscribe = vi.fn(() => { listener = undefined })
  const bridge: DesktopBridge & { emit: (message: DesktopStreamMessage) => void } = {
    request: vi.fn().mockResolvedValue({ ok: true, status: 200, data: { status: 'ready' } }),
    modelConfigTest: vi.fn(),
    modelConfigSave: vi.fn(),
    startStream: vi.fn(),
    cancelStream: vi.fn(),
    onStreamEvent: vi.fn((next) => { listener = next; return unsubscribe }),
    onBackendExit: vi.fn(() => () => {}),
    emit: (message) => listener?.(message),
  }
  return { bridge, unsubscribe }
}

describe('Desktop transport', () => {
  it('converts desktop envelopes into typed results and user-safe errors', async () => {
    const { bridge } = fakeBridge()
    const transport = createDesktopTransport(bridge)

    await expect(transport.request({ method: 'GET', path: '/health/ready' })).resolves.toEqual({ status: 'ready' })
    vi.mocked(bridge.request).mockResolvedValueOnce({
      ok: false,
      status: 503,
      error: { code: 'DESKTOP_BACKEND_UNAVAILABLE', message: '本地学习服务暂时不可用。', retryable: true },
    })
    await expect(transport.request({ method: 'GET', path: '/health/ready' })).rejects.toMatchObject({
      name: 'DesktopApiError',
      code: 'DESKTOP_BACKEND_UNAVAILABLE',
      retryable: true,
    })
  })

  it('subscribes before starting, forwards only its own stream, and cancels its own stream', async () => {
    const { bridge, unsubscribe } = fakeBridge()
    const transport = createDesktopTransport(bridge)
    const controller = new AbortController()
    const events: string[] = []

    const promise = transport.stream(
      { method: 'POST', path: '/api/chat/stream', body: { session_id: 'student_1', message: 'hi' } },
      event => events.push(event.content || event.event),
      controller.signal,
    )

    expect(bridge.onStreamEvent).toHaveBeenCalledTimes(1)
    expect(bridge.startStream).toHaveBeenCalledTimes(1)
    expect(vi.mocked(bridge.onStreamEvent).mock.invocationCallOrder[0]).toBeLessThan(
      vi.mocked(bridge.startStream).mock.invocationCallOrder[0],
    )
    const streamId = vi.mocked(bridge.startStream).mock.calls[0][0]
    bridge.emit({ streamId: 'another_stream', type: 'event', event: { event: 'delta', content: 'ignore' } })
    bridge.emit({ streamId, type: 'event', event: { event: 'delta', content: 'keep' } })
    controller.abort()
    bridge.emit({ streamId, type: 'done' })
    await promise

    expect(events).toEqual(['keep'])
    expect(bridge.cancelStream).toHaveBeenCalledWith(streamId)
    expect(unsubscribe).toHaveBeenCalledTimes(1)
  })

  it('rejects a desktop error event and always releases its subscription', async () => {
    const { bridge, unsubscribe } = fakeBridge()
    const promise = createDesktopTransport(bridge).stream(
      { method: 'POST', path: '/api/chat/stream', body: { session_id: 'student_1', message: 'hi' } },
      () => {},
    )
    const streamId = vi.mocked(bridge.startStream).mock.calls[0][0]
    bridge.emit({
      streamId,
      type: 'error',
      error: { code: 'DESKTOP_STREAM_CANCELLED', message: '生成已取消。', retryable: false },
    })

    await expect(promise).rejects.toBeInstanceOf(DesktopApiError)
    expect(unsubscribe).toHaveBeenCalledTimes(1)
  })
})
