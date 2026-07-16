import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import type { ModelConfigInput, ModelProfileInput } from '@/api/types'

const apiMock = vi.hoisted(() => ({
  live: vi.fn(), ready: vi.fn(), modelSettings: vi.fn(), session: vi.fn(), progress: vi.fn(),
  nextAction: vi.fn(), reviews: vi.fn(), mistakes: vi.fn(), submitAttempt: vi.fn(),
  testModelSettings: vi.fn(), saveModelSettings: vi.fn(),
  modelProfilesList: vi.fn(), modelRuntimeStatus: vi.fn(), testModelProfile: vi.fn(),
  upsertModelProfile: vi.fn(), deleteModelProfile: vi.fn(), saveModelProfilePolicy: vi.fn(),
  sessionModelPreference: vi.fn(), saveSessionModelPreference: vi.fn(),
  knowledgeStatus: vi.fn(), knowledgeCollections: vi.fn(), knowledgeDocuments: vi.fn(),
  knowledgeImports: vi.fn(), sessionKnowledgeCollections: vi.fn(),
  saveSessionKnowledgeCollections: vi.fn(),
  retryResourceArtifact: vi.fn(),
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
  }], resource_bundles: [],
}

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((onResolve, onReject) => { resolve = onResolve; reject = onReject })
  return { promise, resolve, reject }
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
  apiMock.modelProfilesList.mockResolvedValue({ version: 2, global: { default_profile_id: 'primary', auto_failover: true, fallback_profile_ids: [] }, profiles: [{ id: 'primary', label: '主模型', enabled: true, provider: 'openai', base_url: 'https://example.com', api_key_configured: true, anthropic_version: '2023-06-01', request_timeout_seconds: 60, default_model_id: 'model-a', models: [{ id: 'model-a', provider_model_name: 'test', label: 'Test', max_output_tokens: 4096, supported_reasoning_efforts: ['auto', 'off'], reasoning_adapter: 'none' }] }] })
  apiMock.modelRuntimeStatus.mockResolvedValue({ ready: true, default_profile_id: 'primary', auto_failover: true, fallback_profile_ids: [], profiles: [] })
  apiMock.testModelProfile.mockResolvedValue({ provider: 'openai', model_name: 'test', status: 'connected', latency_ms: 8 })
  apiMock.upsertModelProfile.mockImplementation(async () => ({ vault: await apiMock.modelProfilesList(), runtime: await apiMock.modelRuntimeStatus() }))
  apiMock.deleteModelProfile.mockImplementation(async () => ({ vault: await apiMock.modelProfilesList(), runtime: await apiMock.modelRuntimeStatus() }))
  apiMock.saveModelProfilePolicy.mockImplementation(async () => ({ vault: await apiMock.modelProfilesList(), runtime: await apiMock.modelRuntimeStatus() }))
  apiMock.sessionModelPreference.mockImplementation(async (sessionId: string) => ({ session_id: sessionId, profile_mode: 'auto', preferred_profile_id: null, model_id: null, reasoning_effort: 'auto', failover_override: 'inherit' }))
  apiMock.saveSessionModelPreference.mockImplementation(async (sessionId: string, input: object) => ({ session_id: sessionId, ...input }))
  apiMock.knowledgeStatus.mockResolvedValue({ fts: { available: true, mode: 'keyword' } })
  apiMock.knowledgeCollections.mockResolvedValue([{ id: 1, name: '高数', description: '', color: '#c98f65', document_count: 1, bound_session_count: 0, created_at: '', updated_at: '' }])
  apiMock.knowledgeDocuments.mockResolvedValue([])
  apiMock.knowledgeImports.mockResolvedValue([])
  apiMock.sessionKnowledgeCollections.mockResolvedValue({ session_id: 'test-session', collection_ids: [1], privacy_mode: 'allow_model_context' })
  apiMock.saveSessionKnowledgeCollections.mockResolvedValue({ session_id: 'test-session', collection_ids: [2], privacy_mode: 'allow_model_context' })
  apiMock.retryResourceArtifact.mockResolvedValue({ bundle: { bundle_id: 'b1', artifacts: [] } })
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

  it('exposes bundle history and replaces a retried bundle in place', async () => {
    const original = { bundle_id: 'b1', artifacts: [{ type: 'mind_map', status: 'FAILED' }] }
    const updated = { bundle_id: 'b1', artifacts: [{ type: 'mind_map', status: 'SUCCEEDED' }] }
    apiMock.session.mockResolvedValueOnce({ ...session, resource_bundles: [original] })
    apiMock.retryResourceArtifact.mockResolvedValueOnce({ bundle: updated })
    const store = useBackendStore()

    await store.refreshSession()
    expect(store.resourceBundles).toEqual([original])
    await store.retryResourceArtifact('b1', 'mind_map')

    expect(apiMock.retryResourceArtifact).toHaveBeenCalledWith('b1', 'mind_map', store.sessionId)
    expect(store.resourceBundles).toEqual([updated])
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
    const input: ModelConfigInput = {
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

  it('refreshes profile summaries and runtime status independently without clearing profiles on status failure', async () => {
    const store = useBackendStore()
    await store.refreshModelProfiles()
    expect(store.modelProfiles).toHaveLength(1)

    apiMock.modelRuntimeStatus.mockRejectedValue(new Error('status unavailable'))
    await store.refreshModelProfiles()

    expect(store.modelProfiles).toHaveLength(1)
    expect(store.modelPolicy?.default_profile_id).toBe('primary')
  })

  it('serializes overlapping profile refreshes so an older response cannot overwrite newer state', async () => {
    const oldRefresh = deferred<any>()
    const oldVault = await apiMock.modelProfilesList()
    const newVault = {
      ...oldVault,
      profiles: [{ ...oldVault.profiles[0], id: 'new-primary', label: '新主模型' }],
      global: { default_profile_id: 'new-primary', auto_failover: true, fallback_profile_ids: [] },
    }
    apiMock.modelProfilesList.mockClear()
    apiMock.modelProfilesList
      .mockReturnValueOnce(oldRefresh.promise)
      .mockResolvedValueOnce(newVault)
    const store = useBackendStore()

    const first = store.refreshModelProfiles()
    const second = store.refreshModelProfiles()
    await Promise.resolve()
    expect(apiMock.modelProfilesList).toHaveBeenCalledTimes(1)
    oldRefresh.resolve(oldVault)
    await Promise.all([first, second])

    expect(store.modelProfiles[0].id).toBe('new-primary')
  })

  it('loads preferences after switching sessions and rolls back optimistic preference saves', async () => {
    const store = useBackendStore()
    store.setSessionId('space_b')
    await vi.waitFor(() => expect(apiMock.sessionModelPreference).toHaveBeenCalledWith('space_b'))
    expect(store.sessionModelPreference?.session_id).toBe('space_b')

    apiMock.saveSessionModelPreference.mockRejectedValueOnce(new Error('save failed'))
    const saving = store.saveSessionModelPreference({
      profile_mode: 'manual', preferred_profile_id: 'primary', model_id: 'model-a',
      reasoning_effort: 'high', failover_override: 'off',
    })
    expect(store.sessionModelPreference?.reasoning_effort).toBe('high')
    await expect(saving).rejects.toThrow('save failed')
    expect(store.sessionModelPreference?.reasoning_effort).toBe('auto')
  })

  it('ignores stale A-B-A preference loads and keeps busy until queued saves settle', async () => {
    const firstA = deferred<any>()
    const loadB = deferred<any>()
    const latestA = deferred<any>()
    apiMock.sessionModelPreference
      .mockReturnValueOnce(firstA.promise)
      .mockReturnValueOnce(loadB.promise)
      .mockReturnValueOnce(latestA.promise)
    const store = useBackendStore()
    store.setSessionId('space_a')
    store.setSessionId('space_b')
    store.setSessionId('space_a')
    await vi.waitFor(() => expect(apiMock.sessionModelPreference).toHaveBeenCalledTimes(3))
    latestA.resolve({ session_id: 'space_a', profile_mode: 'auto', preferred_profile_id: null, model_id: null, reasoning_effort: 'high', failover_override: 'inherit' })
    firstA.resolve({ session_id: 'space_a', profile_mode: 'auto', preferred_profile_id: null, model_id: null, reasoning_effort: 'low', failover_override: 'inherit' })
    loadB.resolve({ session_id: 'space_b', profile_mode: 'auto', preferred_profile_id: null, model_id: null, reasoning_effort: 'medium', failover_override: 'inherit' })
    await vi.waitFor(() => expect(store.sessionModelPreference?.reasoning_effort).toBe('high'))

    const firstSave = deferred<any>()
    const secondSave = deferred<any>()
    apiMock.saveSessionModelPreference.mockReturnValueOnce(firstSave.promise).mockReturnValueOnce(secondSave.promise)
    const savingFirst = store.saveSessionModelPreference({ profile_mode: 'auto', preferred_profile_id: null, model_id: null, reasoning_effort: 'low', failover_override: 'inherit' })
    const savingSecond = store.saveSessionModelPreference({ profile_mode: 'auto', preferred_profile_id: null, model_id: null, reasoning_effort: 'medium', failover_override: 'inherit' })
    firstSave.resolve({ session_id: 'space_a', profile_mode: 'auto', preferred_profile_id: null, model_id: null, reasoning_effort: 'low', failover_override: 'inherit' })
    await savingFirst
    expect(store.modelProfileBusy).toBe(true)
    secondSave.resolve({ session_id: 'space_a', profile_mode: 'auto', preferred_profile_id: null, model_id: null, reasoning_effort: 'medium', failover_override: 'inherit' })
    await savingSecond
    expect(store.sessionModelPreference?.reasoning_effort).toBe('medium')
    expect(store.modelProfileBusy).toBe(false)
  })

  it('keeps the latest optimistic preference and rolls back to the last committed value after queued failures', async () => {
    const firstSave = deferred<any>()
    const secondSave = deferred<any>()
    apiMock.saveSessionModelPreference
      .mockReturnValueOnce(firstSave.promise)
      .mockReturnValueOnce(secondSave.promise)
    const store = useBackendStore()
    store.setSessionId('space_a')
    await vi.waitFor(() => expect(store.sessionModelPreference?.session_id).toBe('space_a'))

    const savingFirst = store.saveSessionModelPreference({ profile_mode: 'auto', preferred_profile_id: null, model_id: null, reasoning_effort: 'low', failover_override: 'inherit' })
    const firstFailure = savingFirst.catch(error => error)
    const savingSecond = store.saveSessionModelPreference({ profile_mode: 'auto', preferred_profile_id: null, model_id: null, reasoning_effort: 'medium', failover_override: 'inherit' })
    const secondFailure = savingSecond.catch(error => error)

    expect(store.sessionModelPreference?.reasoning_effort).toBe('medium')
    firstSave.reject(new Error('first save failed'))
    expect((await firstFailure).message).toBe('first save failed')
    await vi.waitFor(() => expect(apiMock.saveSessionModelPreference).toHaveBeenCalledTimes(2))
    expect(store.sessionModelPreference?.reasoning_effort).toBe('medium')
    expect(store.modelProfileBusy).toBe(true)

    secondSave.reject(new Error('second save failed'))
    expect((await secondFailure).message).toBe('second save failed')
    expect(store.sessionModelPreference?.reasoning_effort).toBe('auto')
    expect(store.modelProfileBusy).toBe(false)
  })

  it('exposes one busy transaction for profile test, mutation, deletion and policy save', async () => {
    const store = useBackendStore()
    const input: ModelProfileInput = {
      id: 'primary', label: '主模型', enabled: true, provider: 'openai' as const,
      base_url: 'https://example.com', api_key: '', anthropic_version: '2023-06-01',
      request_timeout_seconds: 60, default_model_id: 'model-a',
      models: [{ id: 'model-a', provider_model_name: 'test', label: 'Test', max_output_tokens: 4096, supported_reasoning_efforts: ['auto', 'off'], reasoning_adapter: 'none' }],
    }
    const policy = { default_profile_id: 'primary', auto_failover: true, fallback_profile_ids: [] }

    await store.testModelProfile(input)
    await store.upsertModelProfile(input)
    await store.deleteModelProfile('backup')
    await store.saveModelPolicy(policy)

    expect(apiMock.testModelProfile).toHaveBeenCalledWith(input)
    expect(apiMock.upsertModelProfile).toHaveBeenCalledWith(input)
    expect(apiMock.deleteModelProfile).toHaveBeenCalledWith('backup')
    expect(apiMock.saveModelProfilePolicy).toHaveBeenCalledWith(policy)
    expect(store.modelProfileBusy).toBe(false)
  })
})
