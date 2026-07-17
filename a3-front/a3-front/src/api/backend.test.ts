import { beforeEach, describe, expect, it, vi } from 'vitest'
import { backendApi, parseSseBlock, readSseBody } from './backend'
import type { ModelProfileInput } from './types'

const webRequest = vi.hoisted(() => vi.fn())
vi.mock('axios', () => ({ default: { create: () => ({ request: webRequest }) } }))

const modelInput = {
  provider: 'openai' as const,
  api_key: 'test-secret-key',
  base_url: 'https://api.example.test',
  model_name: 'test-model',
  anthropic_version: '2023-06-01',
  request_timeout_seconds: 60,
}

const profileInput: ModelProfileInput = {
  id: 'primary', label: '主模型', enabled: true, provider: 'openai' as const,
  base_url: 'https://api.example.test/v1', api_key: 'test-secret-key',
  anthropic_version: '2023-06-01', request_timeout_seconds: 60,
  default_model_id: 'model-a',
  models: [{
    id: 'model-a', provider_model_name: 'test-model', label: 'Test Model',
    max_output_tokens: 4096, supported_reasoning_efforts: ['auto', 'off'],
    reasoning_adapter: 'none' as const,
  }],
}

const profileVault = {
  version: 2 as const,
  global: { default_profile_id: 'primary', auto_failover: true, fallback_profile_ids: [] },
  profiles: [{ ...profileInput, api_key_configured: true, api_key: undefined }],
}

const runtimeStatus = {
  ready: true, default_profile_id: 'primary', auto_failover: true, fallback_profile_ids: [],
  profiles: [{ profile_id: 'primary', enabled: true, needs_attention: false, circuit_state: 'closed', cooldown_until: 0, consecutive_failures: 0 }],
}

beforeEach(() => {
  delete window.a3Desktop
  webRequest.mockReset()
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

describe('resource bundle API contracts', () => {
  it('sends bundle and single selections through chat and stream', async () => {
    const request = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      data: { reply: '', phase: 'resource', state: 'PROFILED', profile_version: 1, cached: false, sources: [], knowledge_sources: [], bundle: null },
    })
    let streamHandler: ((message: any) => void) | undefined
    const startStream = vi.fn((streamId: string, input: unknown) => {
      queueMicrotask(() => streamHandler?.({ streamId, type: 'done' }))
      return input
    })
    window.a3Desktop = {
      request,
      modelConfigTest: vi.fn(),
      modelConfigSave: vi.fn(),
      startStream,
      cancelStream: vi.fn(),
      onStreamEvent: vi.fn(handler => {
        streamHandler = handler
        return () => {}
      }),
      onBackendExit: vi.fn(() => () => {}),
    }

    await backendApi.chat('s1', '生成全部', { mode: 'bundle' })
    await backendApi.streamChat(
      's1',
      '生成导图',
      vi.fn(),
      undefined,
      { mode: 'single', resourceType: 'mind_map' },
    )

    expect(request).toHaveBeenCalledWith({
      method: 'POST',
      path: '/api/chat',
      body: { session_id: 's1', message: '生成全部', resource_mode: 'bundle' },
    })
    expect(startStream.mock.calls[0][1]).toMatchObject({
      method: 'POST',
      path: '/api/chat/stream',
      body: {
        session_id: 's1',
        message: '生成导图',
        resource_mode: 'single',
        resource_type: 'mind_map',
      },
    })
  })

  it('sends a bounded textbook scope through chat and stream', async () => {
    const request = vi.fn().mockResolvedValue({
      ok: true, status: 200,
      data: { reply: '', phase: 'resource', state: 'PROFILED', profile_version: 1, cached: false, sources: [], knowledge_sources: [], bundle: null },
    })
    let streamHandler: ((message: any) => void) | undefined
    const startStream = vi.fn((streamId: string, input: unknown) => {
      queueMicrotask(() => streamHandler?.({ streamId, type: 'done' }))
      return input
    })
    window.a3Desktop = {
      request, modelConfigTest: vi.fn(), modelConfigSave: vi.fn(), startStream,
      cancelStream: vi.fn(), onStreamEvent: vi.fn(handler => { streamHandler = handler; return () => {} }),
      onBackendExit: vi.fn(() => () => {}),
    }
    const scope = { documentId: 7, pageStart: 12, pageEnd: 36, searchMode: 'expanded' as const }

    await backendApi.chat('s1', '总结教材', { mode: 'bundle' }, scope)
    await backendApi.streamChat('s1', '生成例题', vi.fn(), undefined, { mode: 'bundle' }, scope)

    expect(request.mock.calls[0][0].body.knowledge_scope).toEqual({
      document_id: 7, page_start: 12, page_end: 36, search_mode: 'expanded',
    })
    expect(startStream.mock.calls[0][1]).toMatchObject({
      body: { knowledge_scope: { document_id: 7, page_start: 12, page_end: 36, search_mode: 'expanded' } },
    })
  })

  it('uses the fixed history and artifact retry routes', async () => {
    const request = vi.fn()
      .mockResolvedValueOnce({ ok: true, status: 200, data: { session_id: 's1', messages: [], resources: [], resource_bundles: [] } })
      .mockResolvedValueOnce({ ok: true, status: 200, data: { bundle: { bundle_id: 'b1' } } })
    window.a3Desktop = {
      request,
      modelConfigTest: vi.fn(), modelConfigSave: vi.fn(),
      startStream: vi.fn(), cancelStream: vi.fn(),
      onStreamEvent: vi.fn(() => () => {}), onBackendExit: vi.fn(() => () => {}),
    }

    await backendApi.session('s1')
    await backendApi.retryResourceArtifact('b1', 'mind_map', 's1')

    expect(request).toHaveBeenNthCalledWith(2, {
      method: 'POST',
      path: '/api/resource-bundles/b1/artifacts/mind_map/retry',
      body: { session_id: 's1' },
    })
  })
})

describe('competition demo API', () => {
  it('uses only fixed seed reset and status routes without fixture payloads', async () => {
    const snapshot = {
      session_id: 'demo_offline_v1', seeded: true, mode: 'offline', degradation_message: '模型不可用',
      dataset: { title: '原创演示', license: 'CC0-1.0', original: true, collection_id: 3 },
      agent_steps: [], mastery_before: [], mastery_after: [], routes: { overview: '/dashboard', agents: '/agents', tutor: '/tutor' },
    }
    const request = vi.fn().mockResolvedValue({ ok: true, status: 200, data: snapshot })
    window.a3Desktop = {
      request, modelConfigTest: vi.fn(), modelConfigSave: vi.fn(), startStream: vi.fn(), cancelStream: vi.fn(),
      onStreamEvent: vi.fn(() => () => {}), onBackendExit: vi.fn(() => () => {}),
    }

    await backendApi.demoStatus()
    await backendApi.seedDemo()
    await backendApi.resetDemo()

    expect(request.mock.calls).toEqual([
      [{ method: 'GET', path: '/api/demo/status' }],
      [{ method: 'POST', path: '/api/demo/seed' }],
      [{ method: 'POST', path: '/api/demo/reset' }],
    ])
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

  it('converts a fixed desktop model config error to BackendApiError', async () => {
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
      name: 'BackendApiError',
      code: 'MODEL_AUTHENTICATION_ERROR',
      status: 401,
    })
  })
})

describe('multi-profile model API', () => {
  it('uses only the six fixed desktop bridge methods', async () => {
    const request = vi.fn()
    const modelProfilesList = vi.fn().mockResolvedValue({ ok: true, status: 200, data: profileVault })
    const modelProfileTest = vi.fn().mockResolvedValue({ ok: true, status: 200, data: { provider: 'openai', model_name: 'test-model', status: 'connected', latency_ms: 10 } })
    const mutation = { vault: profileVault, runtime: runtimeStatus }
    const modelProfileUpsert = vi.fn().mockResolvedValue({ ok: true, status: 200, data: mutation })
    const modelProfileDelete = vi.fn().mockResolvedValue({ ok: true, status: 200, data: mutation })
    const modelProfilePolicySave = vi.fn().mockResolvedValue({ ok: true, status: 200, data: mutation })
    const modelRuntimeStatus = vi.fn().mockResolvedValue({ ok: true, status: 200, data: runtimeStatus })
    window.a3Desktop = {
      request, modelConfigTest: vi.fn(), modelConfigSave: vi.fn(),
      modelProfilesList, modelProfileTest, modelProfileUpsert, modelProfileDelete,
      modelProfilePolicySave, modelRuntimeStatus,
      startStream: vi.fn(), cancelStream: vi.fn(),
      onStreamEvent: vi.fn(() => () => {}), onBackendExit: vi.fn(() => () => {}),
    }

    await backendApi.modelProfilesList()
    await backendApi.testModelProfile(profileInput)
    await backendApi.upsertModelProfile(profileInput)
    await backendApi.deleteModelProfile('primary')
    await backendApi.saveModelProfilePolicy(profileVault.global)
    await backendApi.modelRuntimeStatus()

    expect(modelProfilesList).toHaveBeenCalledOnce()
    expect(modelProfileTest).toHaveBeenCalledWith(profileInput)
    expect(modelProfileUpsert).toHaveBeenCalledWith(profileInput)
    expect(modelProfileDelete).toHaveBeenCalledWith('primary')
    expect(modelProfilePolicySave).toHaveBeenCalledWith(profileVault.global)
    expect(modelRuntimeStatus).toHaveBeenCalledOnce()
    expect(request).not.toHaveBeenCalled()
  })

  it('uses public compatibility routes in web mode and never requests internal control paths', async () => {
    webRequest
      .mockResolvedValueOnce({ status: 200, data: { provider: 'openai', base_url: 'https://api.example.test/v1', model_name: 'test-model', api_key_configured: true, api_key_hint: 'configured', anthropic_version: '2023-06-01', request_timeout_seconds: 60 } })
      .mockResolvedValueOnce({ status: 200, data: { status: 'ready' } })
      .mockResolvedValueOnce({ status: 200, data: { provider: 'openai', base_url: 'https://api.example.test/v1', model_name: 'test-model', api_key_configured: true, api_key_hint: 'configured', anthropic_version: '2023-06-01', request_timeout_seconds: 60 } })

    await backendApi.modelProfilesList()
    await backendApi.modelRuntimeStatus()

    expect(webRequest.mock.calls.map(call => call[0].url)).toEqual(['/api/settings/model', '/health/ready', '/api/settings/model'])
    expect(JSON.stringify(webRequest.mock.calls)).not.toContain('/internal/')
  })

  it('does not fall back to generic desktop requests when a fixed bridge method is unavailable', async () => {
    const request = vi.fn()
    window.a3Desktop = {
      request, modelConfigTest: vi.fn(), modelConfigSave: vi.fn(),
      startStream: vi.fn(), cancelStream: vi.fn(),
      onStreamEvent: vi.fn(() => () => {}), onBackendExit: vi.fn(() => () => {}),
    }

    await expect(backendApi.modelProfilesList()).rejects.toMatchObject({
      code: 'DESKTOP_BRIDGE_UNAVAILABLE',
    })
    expect(request).not.toHaveBeenCalled()
  })
})

describe('knowledge API', () => {
  it('sends bounded document filters and bulk commands through fixed routes', async () => {
    const request = vi.fn()
      .mockResolvedValueOnce({ ok: true, status: 200, data: [] })
      .mockResolvedValueOnce({ ok: true, status: 200, data: { items: [{ document_id: 2, ok: true, code: null }] } })
    window.a3Desktop = {
      request, modelConfigTest: vi.fn(), modelConfigSave: vi.fn(),
      startStream: vi.fn(), cancelStream: vi.fn(),
      onStreamEvent: vi.fn(() => () => {}), onBackendExit: vi.fn(() => () => {}),
    }

    await backendApi.knowledgeDocuments({
      collectionId: 3, trash: true, favorite: true, tag: '函数', query: '极限',
      status: 'COMPLETED', sort: 'name', direction: 'asc',
    })
    await backendApi.bulkKnowledgeDocuments({
      action: 'add_to_collections', document_ids: [1, 2], collection_ids: [3], tags: [],
    })

    expect(request).toHaveBeenNthCalledWith(1, {
      method: 'GET', path: '/api/knowledge/documents',
      query: {
        collection_id: 3, trash: true, favorite: true, tag: '函数', query: '极限',
        status: 'COMPLETED', sort: 'name', direction: 'asc',
      },
    })
    expect(request).toHaveBeenNthCalledWith(2, {
      method: 'POST', path: '/api/knowledge/documents/bulk',
      body: { action: 'add_to_collections', document_ids: [1, 2], collection_ids: [3], tags: [] },
    })
  })

  it('loads the textbook catalog and opens official entries through a fixed desktop bridge', async () => {
    const request = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      data: { version: '2026-07-17', items: [] },
    })
    const knowledgeOpenOfficialTextbook = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      data: { sourceId: 'pep-high-math' },
    })
    window.a3Desktop = {
      request,
      modelConfigTest: vi.fn(),
      modelConfigSave: vi.fn(),
      knowledgeOpenOfficialTextbook,
      startStream: vi.fn(),
      cancelStream: vi.fn(),
      onStreamEvent: vi.fn(() => () => {}),
      onBackendExit: vi.fn(() => () => {}),
    }

    await backendApi.textbookCatalog({ stage: '高中', subject: '数学', publisher: '人民教育出版社' })
    await backendApi.openOfficialTextbook('pep-high-math')

    expect(request).toHaveBeenCalledWith({
      method: 'GET',
      path: '/api/knowledge/textbooks',
      query: { stage: '高中', subject: '数学', publisher: '人民教育出版社' },
    })
    expect(knowledgeOpenOfficialTextbook).toHaveBeenCalledWith('pep-high-math')
  })

  it('uses fixed desktop import bridge and posts no renderer paths', async () => {
    const manifest = {
      sha256: 'a'.repeat(64), display_name: 'lesson.txt', extension: '.txt',
      mime_type: 'text/plain', byte_size: 4, object_relpath: 'objects/' + 'a'.repeat(64),
    }
    const knowledgeChooseFiles = vi.fn().mockResolvedValue({
      ok: true, status: 202, data: { jobs: [{ id: 7, document_id: 2, status: 'QUEUED' }] },
    })
    window.a3Desktop = {
      request: vi.fn(), modelConfigTest: vi.fn(), modelConfigSave: vi.fn(),
      knowledgeChooseFiles, knowledgeImportDroppedFiles: vi.fn(),
      knowledgeRevealSource: vi.fn(), knowledgeOpenSource: vi.fn(),
      knowledgeOnImportProgress: vi.fn(() => () => {}),
      startStream: vi.fn(), cancelStream: vi.fn(),
      onStreamEvent: vi.fn(() => () => {}), onBackendExit: vi.fn(() => () => {}),
    }

    await backendApi.chooseKnowledgeFiles(3)

    expect(knowledgeChooseFiles).toHaveBeenCalledWith(3)
    expect(JSON.stringify(knowledgeChooseFiles.mock.calls)).not.toContain(manifest.object_relpath)
  })

  it('uses whitelisted routes for collection management and local search', async () => {
    const request = vi.fn()
      .mockResolvedValueOnce({ ok: true, status: 201, data: { id: 4, name: '高数' } })
      .mockResolvedValueOnce({ ok: true, status: 200, data: { mode: 'keyword', items: [] } })
    window.a3Desktop = {
      request, modelConfigTest: vi.fn(), modelConfigSave: vi.fn(),
      startStream: vi.fn(), cancelStream: vi.fn(),
      onStreamEvent: vi.fn(() => () => {}), onBackendExit: vi.fn(() => () => {}),
    }

    await backendApi.createKnowledgeCollection({ name: '高数', description: '', color: '#c98f65' })
    await backendApi.searchKnowledge('student_1', '极限', 8)

    expect(request).toHaveBeenNthCalledWith(1, {
      method: 'POST', path: '/api/knowledge/collections',
      body: { name: '高数', description: '', color: '#c98f65' },
    })
    expect(request).toHaveBeenNthCalledWith(2, {
      method: 'POST', path: '/api/knowledge/search',
      body: { session_id: 'student_1', query: '极限', limit: 8 },
    })
  })
})

describe('desktop pet API', () => {
  it('uses fixed desktop pet methods without generic transport requests', async () => {
    const request = vi.fn()
    const snapshot = {
      available: true, pet: { id: 'motuan', displayName: '墨团', description: '学习伙伴' },
      settings: { visible: true, scale: 1, speed: 1 }, state: 'idle',
    }
    const petGet = vi.fn().mockResolvedValue({ ok: true, status: 200, data: snapshot })
    const petUpdateSettings = vi.fn().mockResolvedValue({ ok: true, status: 200, data: snapshot })
    const petSetTaskState = vi.fn().mockResolvedValue({ ok: true, status: 200, data: 'review' })
    const petChooseCharacter = vi.fn().mockResolvedValue({ ok: true, status: 200, data: snapshot })
    const petResetCharacter = vi.fn().mockResolvedValue({ ok: true, status: 200, data: snapshot })
    window.a3Desktop = {
      request, modelConfigTest: vi.fn(), modelConfigSave: vi.fn(),
      petGet, petUpdateSettings, petSetTaskState, petChooseCharacter, petResetCharacter,
      startStream: vi.fn(), cancelStream: vi.fn(),
      onStreamEvent: vi.fn(() => () => {}), onBackendExit: vi.fn(() => () => {}),
    }

    await expect(backendApi.pet()).resolves.toEqual(snapshot)
    await backendApi.updatePetSettings({ scale: 1.25 })
    await backendApi.setPetTaskState('review')
    await backendApi.choosePetCharacter()
    await backendApi.resetPetCharacter()

    expect(petUpdateSettings).toHaveBeenCalledWith({ scale: 1.25 })
    expect(petSetTaskState).toHaveBeenCalledWith('review')
    expect(petChooseCharacter).toHaveBeenCalledOnce()
    expect(petResetCharacter).toHaveBeenCalledOnce()
    expect(request).not.toHaveBeenCalled()
  })

  it('returns an unavailable snapshot and no-ops task state in web mode', async () => {
    await expect(backendApi.pet()).resolves.toMatchObject({ available: false, pet: null })
    await expect(backendApi.setPetTaskState('running')).resolves.toBe('running')
    await expect(backendApi.updatePetSettings({ visible: false })).rejects.toMatchObject({ code: 'DESKTOP_ONLY' })
    expect(webRequest).not.toHaveBeenCalled()
  })
})
