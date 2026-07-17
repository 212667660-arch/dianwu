import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createRouter, createMemoryHistory } from 'vue-router'

const apiMock = vi.hoisted(() => ({
  streamChat: vi.fn(), chat: vi.fn(), cancelGeneration: vi.fn(), openKnowledgeSource: vi.fn(),
}))
const DesktopApiErrorMock = vi.hoisted(() => class DesktopApiError extends Error {
  readonly status: number
  readonly code: string

  constructor(status: number, code: string, message: string) {
    super(message)
    this.name = 'DesktopApiError'
    this.status = status
    this.code = code
  }
})
const storeMock = vi.hoisted(() => ({
  ready: true, modelConfigured: true, sessionId: 'test-session', session: null, progress: null, nextAction: null,
  refreshSession: vi.fn(), modelProfiles: [], modelPolicy: null, sessionModelPreference: null, modelProfileBusy: false,
  refreshModelProfiles: vi.fn(), loadSessionModelPreference: vi.fn(), saveSessionModelPreference: vi.fn(),
  knowledgeCollections: [{ id: 3, name: '高数' }], boundKnowledgeCollectionIds: [], knowledgePrivacyMode: 'allow_model_context',
  refreshKnowledge: vi.fn(), saveSessionKnowledgeCollections: vi.fn(),
  retryResourceArtifact: vi.fn(), resourceBundles: [],
}))
const storeHarness = vi.hoisted(() => ({ current: null as null | typeof storeMock }))
const petMock = vi.hoisted(() => ({
  begin: vi.fn(), update: vi.fn(), complete: vi.fn(), fail: vi.fn(),
}))

vi.mock('@/api', () => ({
  backendApi: apiMock,
  DesktopApiError: DesktopApiErrorMock,
  errorMessage: (error: unknown) => error instanceof Error ? error.message : '请求失败',
}))
vi.mock('@/stores/backend', async () => {
  const { reactive } = await import('vue')
  const store = reactive(storeMock) as typeof storeMock
  storeHarness.current = store
  return { useBackendStore: () => store }
})
vi.mock('element-plus', () => ({ ElMessage: { error: vi.fn(), info: vi.fn(), success: vi.fn() } }))
vi.mock('@/pet/task-state', () => ({
  petTaskState: {
    begin: petMock.begin,
  },
}))

import SmartTutor from './SmartTutor.vue'

const backendStore = storeHarness.current!

const stubs = {
  ElIcon: { template: '<i><slot /></i>' },
  ElInput: { props: ['modelValue'], emits: ['update:modelValue'], template: '<textarea :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />' },
  ElButton: { props: ['disabled'], emits: ['click'], template: '<button :disabled="disabled" @click="$emit(\'click\')"><slot /></button>' },
  ElSwitch: { template: '<input type="checkbox" />' },
  ModelSelectionPopover: { props: ['profiles', 'policy', 'preference', 'busy', 'effectiveProfileId', 'effectiveModelId', 'effectiveReasoningEffort'], emits: ['save'], template: '<button data-testid="model-selector-stub">model {{ effectiveProfileId }}</button>' },
}

describe('SmartTutor failure recovery', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    backendStore.modelConfigured = true
    backendStore.sessionId = 'test-session'
    backendStore.session = null
    backendStore.resourceBundles = []
    backendStore.refreshSession.mockResolvedValue(undefined)
    backendStore.refreshModelProfiles.mockResolvedValue(undefined)
    backendStore.loadSessionModelPreference.mockResolvedValue(undefined)
    backendStore.saveSessionModelPreference.mockResolvedValue(undefined)
    petMock.begin.mockReset().mockReturnValue({ update: petMock.update, complete: petMock.complete, fail: petMock.fail })
    petMock.update.mockReset()
    petMock.complete.mockReset()
    petMock.fail.mockReset()
    apiMock.streamChat.mockImplementation(async (_sessionId, _message, onEvent) => {
      onEvent({ event: 'error', code: 'FIELD_REQUIRED', message: '模型输出缺少必填字段，请重试。' })
    })
  })

  it('maps generation, validation, completion and failure to pet task states', async () => {
    apiMock.streamChat.mockImplementationOnce(async (_sessionId, _message, onEvent) => {
      onEvent({ event: 'phase', phase: 'diagnosis' })
      onEvent({ event: 'validation', valid: true })
      onEvent({ event: 'delta', content: '完成。' })
    })
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/tutor', component: SmartTutor }] })
    await router.push('/tutor'); await router.isReady()
    const wrapper = mount(SmartTutor, { global: { plugins: [router], stubs } })
    await wrapper.get('textarea').setValue('测试桌宠状态')
    await wrapper.get('[data-testid="send"]').trigger('click')
    await flushPromises()

    expect(petMock.begin).toHaveBeenCalledWith('running')
    expect(petMock.update).toHaveBeenCalledWith('running')
    expect(petMock.update).toHaveBeenCalledWith('review')
    expect(petMock.complete).toHaveBeenCalledWith('waiting')

    apiMock.streamChat.mockRejectedValueOnce(new Error('连接失败'))
    await wrapper.get('textarea').setValue('再次测试')
    await wrapper.get('[data-testid="send"]').trigger('click')
    await flushPromises()
    expect(petMock.fail).toHaveBeenCalled()
  })

  it('sends the selected resource mode from the composer', async () => {
    backendStore.session = { state: 'PROFILED', messages: [], resource_bundles: [] } as any
    apiMock.streamChat.mockResolvedValue(undefined)
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/tutor', component: SmartTutor }] })
    await router.push('/tutor'); await router.isReady()
    const wrapper = mount(SmartTutor, { global: { plugins: [router], stubs } })

    await wrapper.get('[data-testid="resource-mode"]').setValue('single:mind_map')
    await wrapper.get('textarea').setValue('生成导图')
    await wrapper.findAll('button').find(button => button.text() === '发送')!.trigger('click')
    await flushPromises()

    expect(apiMock.streamChat).toHaveBeenCalledWith(
      'test-session',
      '生成导图',
      expect.any(Function),
      expect.any(AbortSignal),
      { mode: 'single', resourceType: 'mind_map' },
    )
  })

  it('renders resource progress and the final bundle', async () => {
    backendStore.session = { state: 'PROFILED', messages: [], resource_bundles: [] } as any
    apiMock.streamChat.mockImplementation(async (_sessionId, _message, onEvent) => {
      onEvent({ event: 'resource_progress', current_type: 'course_explanation', completed_count: 1, total_count: 5, status: 'SUCCEEDED' })
      onEvent({
        event: 'resource_artifact', artifact_id: 'b1-course', type: 'course_explanation',
        title: '课程讲解', status: 'SUCCEEDED', body: '## 内容\n讲解', type_specific_data: {},
        quality_score: 90, quality_issues: [], error_code: null, retryable: false,
      })
      onEvent({
        event: 'resource_bundle', bundle_id: 'b1', protocol_version: 'learning-resource-bundle/v2',
        topic: '一次函数', profile_version: 1, learning_state_version: '1', mode: 'bundle',
        status: 'COMPLETED', requested_types: ['course_explanation'],
        artifacts: [{ artifact_id: 'b1-course', type: 'course_explanation', title: '课程讲解', status: 'SUCCEEDED', body: '## 内容\n讲解', type_specific_data: {}, quality_score: 90, quality_issues: [], error_code: null, retryable: false }],
        aggregate_quality: 90, created_at: '2026-07-17T00:00:00Z', knowledge_sources: [], public_sources: [],
      })
    })
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/tutor', component: SmartTutor }] })
    await router.push('/tutor'); await router.isReady()
    const wrapper = mount(SmartTutor, { global: { plugins: [router], stubs } })

    await wrapper.get('textarea').setValue('生成资源')
    await wrapper.findAll('button').find(button => button.text() === '发送')!.trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('1 / 5')
    expect(wrapper.find('.resource-bundle').exists()).toBe(true)
  })

  it('restores bundles from history and retries one artifact', async () => {
    let resolveRetry!: () => void
    backendStore.retryResourceArtifact.mockReturnValue(new Promise<void>(resolve => { resolveRetry = resolve }))
    backendStore.session = { state: 'PROFILED', messages: [], resource_bundles: [] } as any
    backendStore.resourceBundles = [{
      bundle_id: 'history-b1', protocol_version: 'learning-resource-bundle/v2', topic: '一次函数',
      profile_version: 1, learning_state_version: '1', mode: 'bundle', status: 'PARTIAL',
      requested_types: ['mind_map'], aggregate_quality: 0, created_at: '2026-07-17T00:00:00Z',
      knowledge_sources: [], public_sources: [], artifacts: [{
        artifact_id: 'history-b1-mind', type: 'mind_map', title: '思维导图', status: 'FAILED',
        body: '', type_specific_data: {}, quality_score: 0, quality_issues: ['FAILED'],
        error_code: 'SPECIALIST_FAILED', retryable: true,
      }],
    }] as any
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/tutor', component: SmartTutor }] })
    await router.push('/tutor'); await router.isReady()
    const wrapper = mount(SmartTutor, { global: { plugins: [router], stubs } })
    const historical = wrapper.find('.resource-bundle')
    await historical.find('.card-header').trigger('click')
    await historical.find('.retry-btn').trigger('click')
    await Promise.resolve()

    expect(backendStore.retryResourceArtifact).toHaveBeenCalledWith('history-b1', 'mind_map')
    expect(historical.find('.retry-btn').attributes('disabled')).toBeDefined()
    resolveRetry()
    await flushPromises()
  })

  it('keeps a streaming failure visible and restores the draft for retry', async () => {
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/tutor', component: SmartTutor }] })
    await router.push('/tutor')
    await router.isReady()
    const wrapper = mount(SmartTutor, { global: { plugins: [router], stubs } })
    const textarea = wrapper.get('textarea')
    await textarea.setValue('请帮助我学习一次函数')
    const buttons = wrapper.findAll('button')
    const send = buttons.find(button => button.text() === '发送')
    expect(send).toBeDefined()
    await send!.trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('本次请求未完成')
    expect(wrapper.text()).toContain('模型输出缺少必填字段，请重试。')
    const retry = wrapper.findAll('button').find(button => button.text() === '重新编辑')
    expect(retry).toBeDefined()
    await retry!.trigger('click')
    expect((wrapper.get('textarea').element as HTMLTextAreaElement).value).toBe('请帮助我学习一次函数')
  })

  it('treats desktop stream cancellation as cancellation and releases the generation', async () => {
    apiMock.cancelGeneration.mockResolvedValue({ cancelled: true })
    apiMock.streamChat.mockImplementation(async (_sessionId, _message, onEvent, signal) => {
      onEvent({ event: 'delta', generation_id: 'generation_1', content: '正在生成' })
      await new Promise((_, reject) => signal?.addEventListener('abort', () => {
        reject(new DesktopApiErrorMock(499, 'DESKTOP_STREAM_CANCELLED', '生成已取消。'))
      }, { once: true }))
    })
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/tutor', component: SmartTutor }] })
    await router.push('/tutor')
    await router.isReady()
    const wrapper = mount(SmartTutor, { global: { plugins: [router], stubs } })
    await wrapper.get('textarea').setValue('测试取消')
    const send = wrapper.findAll('button').find(button => button.text() === '发送')
    await send!.trigger('click')
    await flushPromises()
    backendStore.sessionId = 'new-session'
    await flushPromises()

    expect(apiMock.cancelGeneration).toHaveBeenCalledWith('generation_1', 'test-session')
    expect(wrapper.text()).not.toContain('本次请求未完成')
    expect(wrapper.text()).not.toContain('桌面令牌')
    expect(wrapper.text()).not.toContain('正在生成')
  })

  it('disables model sending while credentials are not configured', async () => {
    backendStore.modelConfigured = false
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/tutor', component: SmartTutor }] })
    await router.push('/tutor')
    await router.isReady()
    const wrapper = mount(SmartTutor, { global: { plugins: [router], stubs } })
    await wrapper.get('textarea').setValue('不应发送')
    const send = wrapper.findAll('button').find(button => button.text() === '发送')

    expect(send).toBeDefined()
    expect(send!.attributes('disabled')).toBeDefined()
    await send!.trigger('click')
    expect(apiMock.streamChat).not.toHaveBeenCalled()
    expect(apiMock.chat).not.toHaveBeenCalled()
  })

  it('opens with a warm companion welcome and fills a starter into the composer', async () => {
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/tutor', component: SmartTutor }] })
    await router.push('/tutor')
    await router.isReady()
    const wrapper = mount(SmartTutor, { global: { plugins: [router], stubs } })

    expect(wrapper.text()).toContain('今天想一起学点什么？')
    expect(wrapper.text()).toContain('学习伙伴')
    expect(wrapper.find('[data-companion-id="study-companion"]').exists()).toBe(true)
    const starter = wrapper.findAll('button').find(button => button.text().includes('一次函数'))
    expect(starter).toBeDefined()
    await starter!.trigger('click')
    expect((wrapper.get('textarea').element as HTMLTextAreaElement).value).toContain('一次函数')
  })

  it('updates the composer when a suggestion changes on the reused tutor route', async () => {
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/tutor', component: SmartTutor }] })
    await router.push('/tutor')
    await router.isReady()
    const wrapper = mount(SmartTutor, { global: { plugins: [router], stubs } })

    await router.push({ path: '/tutor', query: { prompt: '复习一次函数斜率' } })
    await flushPromises()

    expect((wrapper.get('textarea').element as HTMLTextAreaElement).value).toBe('复习一次函数斜率')
  })

  it('hydrates a bounded prompt and binds the routed knowledge collection without auto-sending', async () => {
    let finishBinding!: () => void
    backendStore.saveSessionKnowledgeCollections.mockImplementation(() => new Promise<void>(resolve => { finishBinding = resolve }))
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/tutor', component: SmartTutor }] })
    await router.push({ path: '/tutor', query: { knowledge_collection: '3', prompt: '总结教材中的极限知识点' } })
    await router.isReady()
    const wrapper = mount(SmartTutor, { global: { plugins: [router], stubs } })
    await Promise.resolve()

    expect((wrapper.get('textarea').element as HTMLTextAreaElement).value).toBe('')
    expect(wrapper.get('[data-testid="send"]').attributes('disabled')).toBeDefined()

    finishBinding()
    await flushPromises()

    expect((wrapper.get('textarea').element as HTMLTextAreaElement).value).toBe('总结教材中的极限知识点')
    expect(backendStore.saveSessionKnowledgeCollections).toHaveBeenCalledWith([3], 'allow_model_context')
    expect(apiMock.streamChat).not.toHaveBeenCalled()
  })

  it('keeps a textbook prompt blocked and retryable when routed binding fails', async () => {
    backendStore.saveSessionKnowledgeCollections.mockRejectedValue(new Error('教材集合绑定失败'))
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/tutor', component: SmartTutor }] })
    await router.push({ path: '/tutor', query: { knowledge_collection: '3', prompt: '总结教材中的极限知识点' } })
    await router.isReady()
    const wrapper = mount(SmartTutor, { global: { plugins: [router], stubs } })
    await flushPromises()

    expect((wrapper.get('textarea').element as HTMLTextAreaElement).value).toBe('')
    expect(wrapper.get('[data-testid="send"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('[data-testid="route-knowledge-error"]').text()).toContain('教材集合绑定失败')
    expect(router.currentRoute.value.query).toMatchObject({ knowledge_collection: '3', prompt: '总结教材中的极限知识点' })
    expect(apiMock.streamChat).not.toHaveBeenCalled()
  })

  it('saves local-only knowledge binding after showing the privacy notice', async () => {
    backendStore.refreshKnowledge.mockResolvedValue(undefined)
    backendStore.saveSessionKnowledgeCollections.mockResolvedValue(undefined)
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/tutor', component: SmartTutor }] })
    await router.push('/tutor'); await router.isReady()
    const wrapper = mount(SmartTutor, { global: { plugins: [router], stubs } })
    await wrapper.get('[data-testid="knowledge-space-button"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-testid="collection-check-3"]').setValue(true)
    expect(wrapper.text()).toContain('少量资料片段会发送给当前模型服务')
    await wrapper.get('[data-testid="privacy-local-only"]').setValue(true)
    await wrapper.get('[data-testid="save-knowledge-binding"]').trigger('click')
    expect(backendStore.saveSessionKnowledgeCollections).toHaveBeenCalledWith([3], 'local_search_only')
  })

  it('opens a local citation in the knowledge-library inspector', async () => {
    apiMock.openKnowledgeSource.mockResolvedValue({ mode: 'readonly-copy' })
    apiMock.streamChat.mockImplementation(async (_sessionId, _message, onEvent) => {
      onEvent({
        event: 'knowledge_sources',
        sources: [{
          reference_id: '资料1', document_id: 9, document_name: '极限讲义.pdf',
          locator_label: '第 3 页', locator: { type: 'page', start: 3, end: 3 },
          chunk_id: 11, retrieval_mode: 'keyword',
        }],
      })
    })
    const KnowledgeTarget = { template: '<div>知识库详情</div>' }
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/tutor', component: SmartTutor },
        { path: '/knowledge', component: KnowledgeTarget },
      ],
    })
    await router.push('/tutor')
    await router.isReady()
    const wrapper = mount(SmartTutor, { global: { plugins: [router], stubs } })
    await wrapper.get('textarea').setValue('用本地讲义解释极限')
    await wrapper.findAll('button').find(button => button.text() === '发送')!.trigger('click')
    await flushPromises()

    await wrapper.get('[aria-label="查看资料1：极限讲义.pdf 第3页"]').trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.path).toBe('/knowledge')
    expect(router.currentRoute.value.query).toMatchObject({ document: '9', type: 'page', start: '3', end: '3' })
    expect(apiMock.openKnowledgeSource).not.toHaveBeenCalled()
  })

  it('keeps partial text after a stream interruption and continues through a new request', async () => {
    let calls = 0
    apiMock.streamChat.mockImplementation(async (_sessionId, message, onEvent) => {
      calls += 1
      if (calls === 1) {
        onEvent({ event: 'meta', profile_id: 'backup', model_id: 'model-b', requested_reasoning_effort: 'high', effective_reasoning_effort: 'medium', failover_used: true })
        onEvent({ event: 'delta', content: '已经写出的部分。' })
        onEvent({ event: 'interrupted', code: 'MODEL_STREAM_INTERRUPTED', can_continue_with_backup: true })
        return
      }
      expect(message).toContain('刚才的回答因连接中断')
      expect(message).not.toContain('API Key')
      onEvent({ event: 'delta', content: '备用连接补完。' })
    })
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/tutor', component: SmartTutor }] })
    await router.push('/tutor'); await router.isReady()
    const wrapper = mount(SmartTutor, { global: { plugins: [router], stubs } })
    await wrapper.get('textarea').setValue('请解释导数')
    await wrapper.findAll('button').find(button => button.text() === '发送')!.trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('已自动切换到备用连接')
    expect(wrapper.get('.message-list [data-testid="failover-notice"]').text()).toContain('已自动切换到备用连接')
    expect(wrapper.text()).toContain('已经写出的部分。')
    expect(wrapper.text()).not.toContain('正在组织思绪')
    const continueButton = wrapper.findAll('button').find(button => button.text() === '使用备用配置继续')
    expect(continueButton).toBeDefined()
    await continueButton!.trigger('click')
    await flushPromises()

    expect(apiMock.streamChat).toHaveBeenCalledTimes(2)
    expect(wrapper.text()).toContain('已经写出的部分。')
  })

  it('clears the previous space effective model when switching sessions', async () => {
    apiMock.streamChat.mockImplementation(async (_sessionId, _message, onEvent) => {
      onEvent({ event: 'meta', profile_id: 'backup', model_id: 'model-b', effective_reasoning_effort: 'medium', failover_used: true })
      onEvent({ event: 'delta', content: '完成。' })
    })
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/tutor', component: SmartTutor }] })
    await router.push('/tutor'); await router.isReady()
    const wrapper = mount(SmartTutor, { global: { plugins: [router], stubs } })
    await wrapper.get('textarea').setValue('测试空间模型')
    await wrapper.findAll('button').find(button => button.text() === '发送')!.trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-testid="model-selector-stub"]').text()).toContain('backup')

    backendStore.sessionId = 'next-space'
    await flushPromises()
    expect(wrapper.get('[data-testid="model-selector-stub"]').text()).not.toContain('backup')
  })
})
