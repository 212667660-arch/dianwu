import { createDesktopTransport } from './desktop-transport'
import { desktopEnvelope, type BackendTransport } from './transport'
import { createWebTransport, parseSseBlock, readSseBody } from './web-transport'
import type {
  AttemptResponse,
  ChatResponse,
  HealthStatus,
  MistakeItem,
  ModelConfigInput,
  ModelConnectionTest,
  ModelSettings,
  NextAction,
  ProgressSnapshot,
  ReviewTask,
  SessionHistory,
  StreamEvent,
} from './types'

function activeTransport(): BackendTransport {
  if (window.a3Desktop) return createDesktopTransport(window.a3Desktop)
  return createWebTransport()
}

export { parseSseBlock, readSseBody }

export const backendApi = {
  async live() {
    return activeTransport().request<HealthStatus>({ method: 'GET', path: '/health/live' })
  },
  async ready() {
    return activeTransport().request<HealthStatus>({ method: 'GET', path: '/health/ready' })
  },
  async modelSettings() {
    return activeTransport().request<ModelSettings>({ method: 'GET', path: '/api/settings/model' })
  },
  async testModelSettings(input: ModelConfigInput) {
    if (window.a3Desktop) {
      return desktopEnvelope<ModelConnectionTest>(await window.a3Desktop.modelConfigTest(input))
    }
    return activeTransport().request<ModelConnectionTest>({
      method: 'POST', path: '/api/settings/model/test', body: input,
    })
  },
  async saveModelSettings(input: ModelConfigInput) {
    if (window.a3Desktop) {
      return desktopEnvelope<ModelSettings>(await window.a3Desktop.modelConfigSave(input))
    }
    return activeTransport().request<ModelSettings>({
      method: 'PUT', path: '/api/settings/model', body: input,
    })
  },
  async chat(sessionId: string, message: string) {
    return activeTransport().request<ChatResponse>({
      method: 'POST', path: '/api/chat', body: { session_id: sessionId, message },
    })
  },
  async streamChat(sessionId: string, message: string, onEvent: (event: StreamEvent) => void, signal?: AbortSignal) {
    return activeTransport().stream({
      method: 'POST',
      path: '/api/chat/stream',
      body: { session_id: sessionId, message },
    }, onEvent, signal)
  },
  async cancelGeneration(generationId: string, sessionId: string) {
    return activeTransport().request({
      method: 'DELETE',
      path: `/api/generations/${encodeURIComponent(generationId)}`,
      query: { session_id: sessionId },
    })
  },
  async session(sessionId: string) {
    return activeTransport().request<SessionHistory>({
      method: 'GET', path: `/api/sessions/${encodeURIComponent(sessionId)}`,
    })
  },
  async progress(sessionId: string) {
    return activeTransport().request<ProgressSnapshot>({
      method: 'GET', path: `/api/sessions/${encodeURIComponent(sessionId)}/progress`,
    })
  },
  async nextAction(sessionId: string) {
    return activeTransport().request<NextAction>({
      method: 'GET', path: `/api/sessions/${encodeURIComponent(sessionId)}/next-action`,
    })
  },
  async reviews(sessionId: string, dueOnly = false) {
    return activeTransport().request<ReviewTask[]>({
      method: 'GET', path: `/api/sessions/${encodeURIComponent(sessionId)}/reviews`, query: { due_only: dueOnly },
    })
  },
  async mistakes(sessionId: string) {
    return activeTransport().request<MistakeItem[]>({
      method: 'GET', path: `/api/sessions/${encodeURIComponent(sessionId)}/mistakes`,
    })
  },
  async submitAttempt(sessionId: string, questionId: number, answer: string, hintCount = 0) {
    return activeTransport().request<AttemptResponse>({
      method: 'POST',
      path: `/api/sessions/${encodeURIComponent(sessionId)}/questions/${questionId}/attempts`,
      body: { answer, hint_count: hintCount, idempotency_key: `web_${Date.now()}` },
    })
  },
  async rediagnose(sessionId: string) {
    return activeTransport().request({
      method: 'POST', path: `/api/sessions/${encodeURIComponent(sessionId)}/rediagnose`,
    })
  },
}
