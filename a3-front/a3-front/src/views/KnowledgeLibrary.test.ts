import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import type { KnowledgeDocument, KnowledgeImportJob } from '@/api'

const apiMock = vi.hoisted(() => ({
  knowledgeDocuments: vi.fn(),
  createKnowledgeCollection: vi.fn(),
  updateKnowledgeCollection: vi.fn(),
  deleteKnowledgeCollection: vi.fn(),
  openKnowledgeSource: vi.fn(),
  textbookCatalog: vi.fn(),
  openOfficialTextbook: vi.fn(),
}))
const messageMock = vi.hoisted(() => ({ error: vi.fn(), success: vi.fn(), warning: vi.fn() }))
const confirmMock = vi.hoisted(() => vi.fn())

const store = vi.hoisted(() => ({
  knowledgeCollections: [{ id: 3, name: '高数', description: '极限与导数', color: '#c98f65', document_count: 1, bound_session_count: 1, created_at: '', updated_at: '' }],
  knowledgeDocuments: [{ id: 9, sha256: 'a'.repeat(64), display_name: '极限讲义.pdf', extension: '.pdf', mime_type: 'application/pdf', byte_size: 1024, status: 'COMPLETED', page_count: 3, slide_count: null, sheet_count: null, text_characters: 1200, chunk_count: 4, parser_version: 'chunk-v1', safe_error_code: null, created_at: '', updated_at: '' }] as KnowledgeDocument[],
  knowledgeJobs: [] as KnowledgeImportJob[], knowledgeStatus: { fts: { available: true, mode: 'keyword' }, worker: { available: true, mode: 'isolated' }, ocr_pack: { available: false, mode: 'optional' }, semantic_pack: { available: false, mode: 'optional' } },
  knowledgeLoading: false, knowledgeError: '', refreshKnowledge: vi.fn().mockResolvedValue(undefined),
  chooseKnowledgeFiles: vi.fn(), importDroppedKnowledgeFiles: vi.fn(), cancelKnowledgeJob: vi.fn(), deleteKnowledgeDocument: vi.fn(), rebuildKnowledgeDocument: vi.fn(),
}))
vi.mock('@/stores/backend', async () => {
  const { reactive } = await import('vue')
  return { useBackendStore: () => reactive(store) }
})
vi.mock('@/api', () => ({
  backendApi: apiMock,
  errorMessage: (error: unknown) => error instanceof Error ? error.message : '请求失败',
}))
vi.mock('element-plus', () => ({
  ElMessage: messageMock,
  ElMessageBox: { confirm: confirmMock },
}))
import KnowledgeLibrary from './KnowledgeLibrary.vue'

function setDesktopBridge(value: unknown) {
  Object.defineProperty(window, 'a3Desktop', { configurable: true, writable: true, value })
}

beforeEach(() => {
  vi.clearAllMocks()
  delete (window as typeof window & { a3Desktop?: unknown }).a3Desktop
  store.knowledgeCollections = [{ id: 3, name: '高数', description: '极限与导数', color: '#c98f65', document_count: 1, bound_session_count: 1, created_at: '', updated_at: '' }]
  store.knowledgeDocuments = [{ id: 9, sha256: 'a'.repeat(64), display_name: '极限讲义.pdf', extension: '.pdf', mime_type: 'application/pdf', byte_size: 1024, status: 'COMPLETED', page_count: 3, slide_count: null, sheet_count: null, text_characters: 1200, chunk_count: 4, parser_version: 'chunk-v1', safe_error_code: null, created_at: '', updated_at: '' }]
  store.knowledgeJobs = []
  apiMock.knowledgeDocuments.mockResolvedValue(store.knowledgeDocuments)
  apiMock.textbookCatalog.mockResolvedValue({
    version: '2026-07-17',
    items: [{
      source_id: 'pep-high-math', publisher: '人民教育出版社', title: '人教版高中数学教材电子版目录',
      stage: '高中', grade: '必修与选择性必修', semester: '全册', subject: '数学', edition: '人教 A/B 版',
      official_url: 'https://jc.pep.com.cn/?filed=高中&subject=数学', access_mode: 'OFFICIAL_READER',
      license_note: '版权所有，仅打开出版社官方在线阅读页。', verified_at: '2026-07-17', download_url: null,
    }],
  })
  apiMock.openOfficialTextbook.mockResolvedValue({ sourceId: 'pep-high-math' })
  confirmMock.mockResolvedValue(undefined)
})

it('shows and opens the authorized textbook catalog', async () => {
  setDesktopBridge({ knowledgeChooseFiles: vi.fn(), knowledgeOpenOfficialTextbook: vi.fn() })
  const wrapper = mount(KnowledgeLibrary, { global: { stubs: { ElDrawer: { template: '<div><slot /></div>' } } } })
  await flushPromises()

  await wrapper.get('[aria-label="选择高中教材"]').trigger('click')
  expect(wrapper.text()).toContain('人教版高中数学教材电子版目录')
  await wrapper.get('[aria-label="在线阅读 人教版高中数学教材电子版目录"]').trigger('click')
  await flushPromises()

  expect(apiMock.openOfficialTextbook).toHaveBeenCalledWith('pep-high-math')
})

it('launches SmartTutor with the selected collection and a textbook summary prompt', async () => {
  setDesktopBridge({ knowledgeChooseFiles: vi.fn() })
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/knowledge', name: 'KnowledgeLibrary', component: KnowledgeLibrary },
      { path: '/tutor', name: 'SmartTutor', component: { template: '<div>tutor</div>' } },
    ],
  })
  await router.push('/knowledge')
  await router.isReady()
  const wrapper = mount(KnowledgeLibrary, { global: { plugins: [router], stubs: { ElDrawer: { template: '<div><slot /></div>' } } } })
  await flushPromises()

  await wrapper.findAll('[aria-label="总结知识点 极限讲义.pdf"]')[0].trigger('click')
  await flushPromises()

  expect(router.currentRoute.value.name).toBe('SmartTutor')
  expect(router.currentRoute.value.query.knowledge_collection).toBe('3')
  expect(String(router.currentRoute.value.query.prompt)).toContain('总结')
  expect(String(router.currentRoute.value.query.prompt)).toContain('极限讲义.pdf')
})

it('explains why document learning is unavailable without an active collection', async () => {
  store.knowledgeCollections = []
  const wrapper = mount(KnowledgeLibrary, { global: { stubs: { ElDrawer: { template: '<div><slot /></div>' } } } })
  await flushPromises()

  await wrapper.findAll('[aria-label="总结知识点 极限讲义.pdf"]')[0].trigger('click')

  expect(messageMock.warning).toHaveBeenCalledWith('请先选择包含这份资料的知识库集合，再开始总结或例题讲解。')
})

it('shows three safe knowledge panes and selects a document', async () => {
  const wrapper = mount(KnowledgeLibrary, { global: { stubs: { ElButton: { template: '<button><slot /></button>' }, ElDrawer: { template: '<div><slot /></div>' }, ElIcon: true } } })
  await flushPromises()
  expect(wrapper.get('[data-testid="collection-rail"]').text()).toContain('高数')
  expect(wrapper.get('[data-testid="document-grid"]').text()).toContain('极限讲义.pdf')
  await wrapper.get('[aria-label="查看文档 极限讲义.pdf"]').trigger('click')
  expect(wrapper.get('[data-testid="document-inspector"]').text()).toContain('3 页')
  expect(wrapper.html()).not.toContain('object_relpath')
  expect(wrapper.html()).not.toContain('C:\\')
})

it('reloads documents when the learner switches collections', async () => {
  store.knowledgeCollections = [
    ...store.knowledgeCollections,
    { id: 4, name: '物理', description: '力与运动', color: '#8f9d7a', document_count: 1, bound_session_count: 0, created_at: '', updated_at: '' },
  ]
  apiMock.knowledgeDocuments.mockResolvedValue([
    { id: 10, sha256: 'b'.repeat(64), display_name: '牛顿定律.md', extension: '.md', mime_type: 'text/markdown', byte_size: 2048, status: 'COMPLETED', page_count: null, slide_count: null, sheet_count: null, text_characters: 900, chunk_count: 2, parser_version: 'chunk-v1', safe_error_code: null, created_at: '', updated_at: '' },
  ])
  const wrapper = mount(KnowledgeLibrary, { global: { stubs: { ElDrawer: { template: '<div><slot /></div>' } } } })
  await flushPromises()

  await wrapper.get('[aria-label="打开集合 物理"]').trigger('click')
  await flushPromises()

  expect(apiMock.knowledgeDocuments).toHaveBeenCalledWith(4)
  expect(wrapper.get('[data-testid="document-grid"]').text()).toContain('牛顿定律.md')
  expect(wrapper.get('[data-testid="document-grid"]').text()).not.toContain('极限讲义.pdf')
})

it('keeps the previous collection and documents when collection loading fails', async () => {
  store.knowledgeCollections = [
    ...store.knowledgeCollections,
    { id: 4, name: '物理', description: '力与运动', color: '#8f9d7a', document_count: 1, bound_session_count: 0, created_at: '', updated_at: '' },
  ]
  const wrapper = mount(KnowledgeLibrary, { global: { stubs: { ElDrawer: { template: '<div><slot /></div>' } } } })
  await flushPromises()
  apiMock.knowledgeDocuments.mockRejectedValueOnce(new Error('集合读取失败'))

  await wrapper.get('[aria-label="打开集合 物理"]').trigger('click')
  await flushPromises()

  expect(wrapper.get('.center-heading strong').text()).toBe('高数')
  expect(wrapper.get('[data-testid="document-grid"]').text()).toContain('极限讲义.pdf')
  expect(messageMock.error).toHaveBeenCalledWith('集合读取失败')
})

it('ignores a stale collection response after a newer selection', async () => {
  store.knowledgeCollections = [
    ...store.knowledgeCollections,
    { id: 4, name: '物理', description: '力与运动', color: '#8f9d7a', document_count: 1, bound_session_count: 0, created_at: '', updated_at: '' },
  ]
  const wrapper = mount(KnowledgeLibrary, { global: { stubs: { ElDrawer: { template: '<div><slot /></div>' } } } })
  await flushPromises()
  let resolvePhysics!: (documents: KnowledgeDocument[]) => void
  let resolveMath!: (documents: KnowledgeDocument[]) => void
  apiMock.knowledgeDocuments
    .mockImplementationOnce(() => new Promise(resolve => { resolvePhysics = resolve }))
    .mockImplementationOnce(() => new Promise(resolve => { resolveMath = resolve }))

  await wrapper.get('[aria-label="打开集合 物理"]').trigger('click')
  await wrapper.get('[aria-label="打开集合 高数"]').trigger('click')
  resolveMath([store.knowledgeDocuments[0]])
  await flushPromises()
  resolvePhysics([{ id: 10, sha256: 'b'.repeat(64), display_name: '牛顿定律.md', extension: '.md', mime_type: 'text/markdown', byte_size: 2048, status: 'COMPLETED', page_count: null, slide_count: null, sheet_count: null, text_characters: 900, chunk_count: 2, parser_version: 'chunk-v1', safe_error_code: null, created_at: '', updated_at: '' }])
  await flushPromises()

  expect(wrapper.get('.center-heading strong').text()).toBe('高数')
  expect(wrapper.get('[data-testid="document-grid"]').text()).toContain('极限讲义.pdf')
  expect(wrapper.get('[data-testid="document-grid"]').text()).not.toContain('牛顿定律.md')
})

it('loads only the first collection documents on a normal visit', async () => {
  store.knowledgeDocuments = [
    ...store.knowledgeDocuments,
    { id: 10, sha256: 'b'.repeat(64), display_name: '其他集合.md', extension: '.md', mime_type: 'text/markdown', byte_size: 2048, status: 'COMPLETED', page_count: null, slide_count: null, sheet_count: null, text_characters: 900, chunk_count: 2, parser_version: 'chunk-v1', safe_error_code: null, created_at: '', updated_at: '' },
  ]
  apiMock.knowledgeDocuments.mockResolvedValue([store.knowledgeDocuments[0]])

  const wrapper = mount(KnowledgeLibrary, { global: { stubs: { ElDrawer: { template: '<div><slot /></div>' } } } })
  await flushPromises()

  expect(apiMock.knowledgeDocuments).toHaveBeenCalledWith(3)
  expect(wrapper.get('[data-testid="document-grid"]').text()).toContain('极限讲义.pdf')
  expect(wrapper.get('[data-testid="document-grid"]').text()).not.toContain('其他集合.md')
})

it('selects the cited document from the route for inspector preview', async () => {
  store.knowledgeDocuments = [
    ...store.knowledgeDocuments,
    { id: 10, sha256: 'b'.repeat(64), display_name: '引用章节.md', extension: '.md', mime_type: 'text/markdown', byte_size: 2048, status: 'COMPLETED', page_count: null, slide_count: null, sheet_count: null, text_characters: 900, chunk_count: 2, parser_version: 'chunk-v1', safe_error_code: null, created_at: '', updated_at: '' },
  ]
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/knowledge', component: KnowledgeLibrary }],
  })
  await router.push('/knowledge?document=10&type=paragraph&start=4&end=4')
  await router.isReady()

  const wrapper = mount(KnowledgeLibrary, {
    global: { plugins: [router], stubs: { ElDrawer: { template: '<div><slot /></div>' } } },
  })
  await flushPromises()

  expect(wrapper.get('[data-testid="document-inspector"]').text()).toContain('引用章节.md')
})

it('opens a cited desktop preview at the locator carried by the route', async () => {
  setDesktopBridge({ knowledgeChooseFiles: vi.fn() })
  store.knowledgeDocuments = [
    { id: 10, sha256: 'b'.repeat(64), display_name: '引用章节.md', extension: '.md', mime_type: 'text/markdown', byte_size: 2048, status: 'COMPLETED', page_count: null, slide_count: null, sheet_count: null, text_characters: 900, chunk_count: 2, parser_version: 'chunk-v1', safe_error_code: null, created_at: '', updated_at: '' },
  ]
  apiMock.openKnowledgeSource.mockResolvedValue({ mode: 'readonly-copy' })
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/knowledge', component: KnowledgeLibrary }] })
  await router.push('/knowledge?document=10&type=paragraph&start=4&end=4')
  await router.isReady()
  const wrapper = mount(KnowledgeLibrary, { global: { plugins: [router], stubs: { ElDrawer: { template: '<div><slot /></div>' } } } })
  await flushPromises()

  await wrapper.findAll('[aria-label="预览（本地阅读器） 引用章节.md"]')[0].trigger('click')
  await flushPromises()

  expect(apiMock.openKnowledgeSource).toHaveBeenCalledWith(10, { type: 'paragraph', start: 4, end: 4 })
  expect(messageMock.success).toHaveBeenCalledWith('已用本地阅读器打开只读预览。')
})

it('applies desktop import progress and releases the listener on unmount', async () => {
  let progressListener: ((jobs: unknown[]) => void) | undefined
  const dispose = vi.fn()
  const onProgress = vi.fn((listener: (jobs: unknown[]) => void) => {
    progressListener = listener
    return dispose
  })
  setDesktopBridge({
    knowledgeChooseFiles: vi.fn(),
    knowledgeOnImportProgress: onProgress,
  })
  store.knowledgeDocuments[0].status = 'PARSING'
  const wrapper = mount(KnowledgeLibrary, { global: { stubs: { ElDrawer: { template: '<div><slot /></div>' } } } })
  await flushPromises()

  expect(onProgress).toHaveBeenCalledOnce()
  progressListener!([{ id: 7, document_id: 9, status: 'PARSING', progress: 57, stage: 'parsing', retryable: false, safe_error_code: null, cancel_requested: false, version: 2, created_at: '', updated_at: '' }])
  await flushPromises()
  expect(wrapper.get('[role="progressbar"]').attributes('aria-valuenow')).toBe('57')
  progressListener!([{ id: 7, document_id: 9, status: 'COMPLETED', progress: 100, stage: 'completed', retryable: false, safe_error_code: null, cancel_requested: false, version: 3, created_at: '', updated_at: '' }])
  await flushPromises()
  expect(store.refreshKnowledge).toHaveBeenCalledTimes(2)

  wrapper.unmount()
  expect(dispose).toHaveBeenCalledOnce()
})

it('reports a collection deletion failure instead of treating it as dialog cancellation', async () => {
  apiMock.deleteKnowledgeCollection.mockRejectedValue(new Error('删除服务暂时不可用'))
  const wrapper = mount(KnowledgeLibrary, { global: { stubs: { ElDrawer: { template: '<div><slot /></div>' } } } })
  await flushPromises()

  await wrapper.findAll('[aria-label="删除集合 高数"]')[0].trigger('click')
  await flushPromises()

  expect(messageMock.error).toHaveBeenCalledWith('删除服务暂时不可用')
})
