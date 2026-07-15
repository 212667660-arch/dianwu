import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

const apiMock = vi.hoisted(() => ({
  live: vi.fn(), ready: vi.fn(), modelSettings: vi.fn(), session: vi.fn(), progress: vi.fn(),
  nextAction: vi.fn(), reviews: vi.fn(), mistakes: vi.fn(), submitAttempt: vi.fn(),
  testModelSettings: vi.fn(), saveModelSettings: vi.fn(),
  knowledgeStatus: vi.fn(), knowledgeCollections: vi.fn(), knowledgeDocuments: vi.fn(),
  knowledgeImports: vi.fn(), sessionKnowledgeCollections: vi.fn(),
  saveSessionKnowledgeCollections: vi.fn(),
}))

vi.mock('@/api', () => ({
  backendApi: apiMock,
  errorMessage: (error: unknown) => error instanceof Error ? error.message : '请求失败',
}))

import { useBackendStore } from './backend'

const session = {
  session_id: 'test-session', state: 'PROFILED', profile_version: 1, learning_state_version: 2,
  profile_text: '画像', messages: [], resources: [{
    id: 1, topic: '一次函数', content: '笔记', profile_version: 1, learning_state_version: 2,
    sources: [], quality_score: 90, quality_issues: [], questions: [{ id: 7, ordinal: 1, difficulty: '基础', prompt: 'y=2x+1 的斜率？' }],
  }],
}

beforeEach(() => {
  setActivePinia(createPinia())
  vi.clearAllMocks()
  apiMock.live.mockResolvedValue({ status: 'live' })
  apiMock.ready.mockResolvedValue({ status: 'ready' })
  apiMock.modelSettings.mockResolvedValue({ provider: 'openai', base_url: 'https://example.com', model_name: 'test', api_key_configured: true, api_key_hint: '***', anthropic_version: '2023-06-01', request_timeout_seconds: 60 })
  apiMock.session.mockResolvedValue(session)
  apiMock.progress.mockResolvedValue({ session_id: 'test-session', learning_state_version: 2, total_attempts: 1, correct_attempts: 1, accuracy: 1, knowledge_points: [] })
  apiMock.nextAction.mockResolvedValue({ session_id: 'test-session', action: 'PRACTICE', knowledge_point_id: null, knowledge_point: null, recommended_difficulty: '基础', reason: '继续练习', due_at: null, suggested_request: '继续练习' })
  apiMock.reviews.mockResolvedValue([])
  apiMock.mistakes.mockResolvedValue([])
  apiMock.submitAttempt.mockResolvedValue({ attempt_id: 1, question_id: 7, duplicate: false, correct: true, score: 1, submitted_answer: '2', expected_answer: '2', explanation: '斜率是 2', feedback: '正确', error_type: null, mastery_score: 0.6, mastery_label: 'LEARNING', next_review_at: '2026-07-14T00:00:00Z' })
  apiMock.testModelSettings.mockResolvedValue({ provider: 'openai', model_name: 'test', status: 'connected', latency_ms: 12 })
  apiMock.saveModelSettings.mockResolvedValue({ provider: 'openai', base_url: 'https://example.com', model_name: 'test', api_key_configured: true, api_key_hint: '***', anthropic_version: '2023-06-01', request_timeout_seconds: 60 })
  apiMock.knowledgeStatus.mockResolvedValue({ fts: { available: true, mode: 'keyword' } })
  apiMock.knowledgeCollections.mockResolvedValue([{ id: 1, name: '高数', description: '', color: '#c98f65', document_count: 1, bound_session_count: 0, created_at: '', updated_at: '' }])
  apiMock.knowledgeDocuments.mockResolvedValue([])
  apiMock.knowledgeImports.mockResolvedValue([])
  apiMock.sessionKnowledgeCollections.mockResolvedValue({ session_id: 'test-session', collection_ids: [1], privacy_mode: 'allow_model_context' })
  apiMock.saveSessionKnowledgeCollections.mockResolvedValue({ session_id: 'test-session', collection_ids: [2], privacy_mode: 'allow_model_context' })
})

describe('backend store', () => {
  it('refreshes health, learning progress and generated questions together', async () => {
    const store = useBackendStore()
    await store.refreshAll()

    expect(store.live).toBe(true)
    expect(store.ready).toBe(true)
    expect(store.resources).toHaveLength(1)
    expect(store.questions).toEqual(session.resources[0].questions)
    expect(store.nextAction?.action).toBe('PRACTICE')
  })

  it('submits an answer and reloads the learning state', async () => {
    const store = useBackendStore()
    await store.refreshSession()
    const result = await store.submitAnswer(7, '2')

    expect(apiMock.submitAttempt).toHaveBeenCalledWith(store.sessionId, 7, '2', 0)
    expect(result.correct).toBe(true)
    expect(apiMock.session).toHaveBeenCalledTimes(2)
  })

  it('reports an online backend with missing credentials as not configured', async () => {
    apiMock.ready.mockRejectedValue(new Error('503'))
    apiMock.modelSettings.mockResolvedValue({
      provider: 'openai', base_url: 'https://example.com', model_name: 'test',
      api_key_configured: false, api_key_hint: '', anthropic_version: '2023-06-01', request_timeout_seconds: 60,
    })
    const store = useBackendStore()

    await store.refreshHealth()

    expect(store.live).toBe(true)
    expect(store.ready).toBe(false)
    expect(store.modelConfigured).toBe(false)
  })

  it('tests and saves model settings while exposing one busy transaction', async () => {
    const store = useBackendStore()
    const input = {
      provider: 'openai' as const,
      api_key: 'test-secret-key',
      base_url: 'https://example.com',
      model_name: 'test',
      anthropic_version: '2023-06-01',
      request_timeout_seconds: 60,
    }

    await expect(store.testModelSettings(input)).resolves.toMatchObject({ status: 'connected' })
    await expect(store.saveModelSettings(input)).resolves.toMatchObject({ api_key_configured: true })

    expect(apiMock.testModelSettings).toHaveBeenCalledWith(input)
    expect(apiMock.saveModelSettings).toHaveBeenCalledWith(input)
    expect(store.modelConfigured).toBe(true)
    expect(store.modelConfigBusy).toBe(false)
  })

  it('keeps existing collections when one knowledge refresh request fails', async () => {
    const store = useBackendStore()
    await store.refreshKnowledge()
    apiMock.knowledgeStatus.mockRejectedValue(new Error('offline'))

    await store.refreshKnowledge()

    expect(store.knowledgeCollections).toHaveLength(1)
    expect(store.knowledgeStatus).toBeNull()
  })

  it('rolls back session bindings when save fails', async () => {
    const store = useBackendStore()
    await store.refreshKnowledge()
    apiMock.saveSessionKnowledgeCollections.mockRejectedValue(new Error('failed'))

    await expect(store.saveSessionKnowledgeCollections([2])).rejects.toThrow()

    expect(store.boundKnowledgeCollectionIds).toEqual([1])
  })
})
