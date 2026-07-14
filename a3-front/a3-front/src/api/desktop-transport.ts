import type { StreamEvent } from './types'
import { DesktopApiError, desktopEnvelope, type BackendTransport, type DesktopBridge, type DesktopError, type TransportRequest } from './transport'

export function createDesktopTransport(bridge: DesktopBridge): BackendTransport {
  return {
    async request<T>(input: TransportRequest): Promise<T> {
      return desktopEnvelope<T>(await bridge.request(input))
    },
    stream(input, onEvent, signal) {
      return streamFromDesktop(bridge, input, onEvent, signal)
    },
  }
}

function streamFromDesktop(
  bridge: DesktopBridge,
  input: TransportRequest,
  onEvent: (event: StreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const streamId = createStreamId()
  return new Promise((resolve, reject) => {
    let settled = false
    const finish = (error?: Error) => {
      if (settled) return
      settled = true
      unsubscribe()
      signal?.removeEventListener('abort', onAbort)
      if (error) reject(error)
      else resolve()
    }
    const onAbort = () => bridge.cancelStream(streamId)
    const unsubscribe = bridge.onStreamEvent(message => {
      if (message.streamId !== streamId) return
      if (message.type === 'event') onEvent(message.event)
      else if (message.type === 'done') finish()
      else finish(toDesktopApiError(499, message.error))
    })

    signal?.addEventListener('abort', onAbort, { once: true })
    if (signal?.aborted) onAbort()
    bridge.startStream(streamId, input)
  })
}

function createStreamId() {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') return crypto.randomUUID()
  return `stream_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 10)}`
}

function toDesktopApiError(status: number, error: DesktopError) {
  return new DesktopApiError(status, error.code, error.message, error.retryable, error.requestId)
}
