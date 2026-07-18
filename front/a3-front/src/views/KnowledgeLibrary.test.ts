import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import type { KnowledgeDocument, KnowledgeImportJob } from '@/api'

const apiMock = vi.hoisted(() => ({
  knowledgeDocuments: vi.fn(),
  bulkKnowledgeDocuments: vi.fn(),
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
  chooseKnowledgeFiles: vi.fn(), importDroppedKnowledgeFiles: vi.fn(), cancelKnowledgeJob: vi.fn(), deleteKnowledgeDocument: vi.fn(), rebuildKnowledgeDocument: vi.fn(), bulkKnowledgeDocuments: vi.fn(),
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

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((onResolve, onReject) => { resolve = onResolve; reject = onReject })
  return { promise, resolve, reject }
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
  apiMock.bulkKnowledgeDocuments.mockResolvedValue({ items: [] })
  store.chooseKnowledgeFiles.mockResolvedValue({ jobs: [], duplicates: [] })
  store.importDroppedKnowledgeFiles.mockResolvedValue({ jobs: [], duplicates: [] })
  store.bulkKnowledgeDocuments.mockResolvedValue({ items: [] })
  confirmMock.mockResolvedValue(undefined)
})

it('offers advanced filters, select all and recycle-bin bulk actions', async () => {
  store.knowledgeDocuments = [
    { ...store.knowledgeDocuments[0], favorite: true, deleted_at: null, collection_ids: [3], tags: ['函数'] },
    { ...store.knowledgeDocuments[0], id: 10, display_name: '导数.pdf', favorite: false, deleted_at: null, collection_ids: [3], tags: [] },
  ]
  apiMock.knowledgeDocuments.mockResolvedValue(store.knowledgeDocuments)
  const wrapper = mount(KnowledgeLibrary, { global: { stubs: { ElDrawer: { template: '<div><slot /></div>' } } } })
  await flushPromises()

  await wrapper.get('[data-testid="select-all-documents"]').trigger('click')
  expect(wrapper.get('[data-testid="bulk-selection-count"]').text()).toContain('2')
  await wrapper.get('[data-testid="bulk-trash"]').trigger('click')
  await flushPromises()
  expect(store.bulkKnowledgeDocuments).toHaveBeenCalledWith({
    action: 'move_to_trash', document_ids: [9, 10], collection_ids: [], tags: [],
  })

  await wrapper.get('[data-testid="trash-filter"]').setValue(true)
  await wrapper.get('[data-testid="sort-filter"]').setValue('name')
  await flushPromises()
  expect(apiMock.knowledgeDocuments).toHaveBeenLastCalledWith(expect.objectContaining({
    collectionId: 3, trash: true, sort: 'name',
  }))
  expect(wrapper.find('[data-testid="bulk-restore"]').exists()).toBe(true)
  expect(wrapper.find('[data-testid="bulk-purge"]').exists()).toBe(true)
})

it('explains duplicate imports instead of silently deduplicating them', async () => {
  setDesktopBridge({ knowledgeChooseFiles: vi.fn() })
  store.chooseKnowledgeFiles.mockResolvedValueOnce({
    jobs: [],
    duplicates: [{ document_id: 9, display_name: '极限讲义.pdf', collection_ids: [3], action: 'already_present' }],
  })
  const wrapper = mount(KnowledgeLibrary, { global: { stubs: { ElDrawer: { template: '<div><slot /></div>' } } } })
  await flushPromises()

  await wrapper.get('[data-testid="import-knowledge-files"]').trigger('click')
  await flushPromises()

  expect(messageMock.warning).toHaveBeenCalledWith(expect.stringContaining('极限讲义.pdf'))
  expect(messageMock.warning).toHaveBeenCalledWith(expect.stringContaining('已存在'))
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

  expect(apiMock.knowledgeDocuments).toHaveBeenCalledWith({
    collectionId: 4, trash: false, sort: 'created', direction: 'desc',
  })
  expect(wrapper.get('[data-testid="document-grid"]').text()).toContain('牛顿定律.md')
  expect(wrapper.get('[data-testid="document-grid"]').text()).not.toContain('极限讲义.pdf')
})

it('preserves all active filters when switching collections', async () => {
  store.knowledgeCollections = [
    ...store.knowledgeCollections,
    { id: 4, name: '物理', description: '力与运动', color: '#8f9d7a', document_count: 1, bound_session_count: 0, created_at: '', updated_at: '' },
  ]
  const physicsDocument = {
    ...store.knowledgeDocuments[0], id: 10, display_name: '牛顿定律.md', favorite: true, collection_ids: [4], tags: ['力学'],
  }
  const wrapper = mount(KnowledgeLibrary, { global: { stubs: { ElDrawer: { template: '<div><slot /></div>' } } } })
  await flushPromises()

  await wrapper.get('[aria-label="筛选知识库资料"]').setValue('牛顿')
  await wrapper.get('[data-testid="trash-filter"]').setValue(true)
  await wrapper.findAll('.advanced-filters input[type="checkbox"]')[1].setValue(true)
  await wrapper.get('[aria-label="按标签筛选"]').setValue('力学')
  await wrapper.get('[aria-label="按状态筛选"]').setValue('COMPLETED')
  await wrapper.get('[data-testid="sort-filter"]').setValue('name')
  await wrapper.get('[aria-label="排序方向"]').setValue('asc')
  await flushPromises()
  apiMock.knowledgeDocuments.mockClear()
  apiMock.knowledgeDocuments.mockResolvedValueOnce([physicsDocument])

  await wrapper.get('[aria-label="打开集合 物理"]').trigger('click')
  await flushPromises()

  expect(apiMock.knowledgeDocuments).toHaveBeenCalledWith({
    collectionId: 4,
    trash: true,
    favorite: true,
    tag: '力学',
    query: '牛顿',
    status: 'COMPLETED',
    sort: 'name',
    direction: 'asc',
  })
  expect(wrapper.get('[aria-label="打开集合 物理"]').element.closest('.collection-wrap')?.classList.contains('active')).toBe(true)
  expect(wrapper.get('[data-testid="document-grid"]').text()).toContain('牛顿定律.md')
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

it('keeps a pending collection selection when a filter refresh wins the race', async () => {
  store.knowledgeCollections = [
    ...store.knowledgeCollections,
    { id: 4, name: '物理', description: '力与运动', color: '#8f9d7a', document_count: 1, bound_session_count: 0, created_at: '', updated_at: '' },
  ]
  const collectionRefresh = deferred<KnowledgeDocument[]>()
  const filterRefresh = deferred<KnowledgeDocument[]>()
  const physicsDocument = {
    ...store.knowledgeDocuments[0], id: 10, display_name: '牛顿定律.md', collection_ids: [4],
  }
  const wrapper = mount(KnowledgeLibrary, { global: { stubs: { ElDrawer: { template: '<div><slot /></div>' } } } })
  await flushPromises()
  apiMock.knowledgeDocuments.mockClear()
  apiMock.knowledgeDocuments
    .mockReturnValueOnce(collectionRefresh.promise)
    .mockReturnValueOnce(filterRefresh.promise)

  await wrapper.get('[aria-label="打开集合 物理"]').trigger('click')
  await wrapper.get('[aria-label="筛选知识库资料"]').setValue('牛顿')
  expect(apiMock.knowledgeDocuments).toHaveBeenNthCalledWith(2, expect.objectContaining({ collectionId: 4, query: '牛顿' }))

  filterRefresh.resolve([physicsDocument])
  await flushPromises()
  expect(wrapper.get('.center-heading strong').text()).toBe('物理')
  expect(wrapper.get('[data-testid="document-grid"]').text()).toContain('牛顿定律.md')

  collectionRefresh.resolve([{ ...store.knowledgeDocuments[0], display_name: '旧集合响应.md' }])
  await flushPromises()
  expect(wrapper.get('.center-heading strong').text()).toBe('物理')
  expect(wrapper.get('[data-testid="document-grid"]').text()).toContain('牛顿定律.md')
  expect(wrapper.get('[data-testid="document-grid"]').text()).not.toContain('旧集合响应.md')
})

it('commits a pending collection response after a favorite succeeds on the old list', async () => {
  store.knowledgeCollections = [
    ...store.knowledgeCollections,
    { id: 4, name: '物理', description: '力与运动', color: '#8f9d7a', document_count: 1, bound_session_count: 0, created_at: '', updated_at: '' },
  ]
  store.knowledgeDocuments = [{
    ...store.knowledgeDocuments[0], favorite: false, deleted_at: null, collection_ids: [3], tags: [],
  }]
  const collectionRefresh = deferred<KnowledgeDocument[]>()
  const saving = deferred<{ items: { document_id: number; ok: boolean; code: null }[] }>()
  store.bulkKnowledgeDocuments.mockReturnValueOnce(saving.promise)
  const wrapper = mount(KnowledgeLibrary, { global: { stubs: { ElDrawer: { template: '<div><slot /></div>' } } } })
  await flushPromises()
  apiMock.knowledgeDocuments.mockClear()
  apiMock.knowledgeDocuments.mockReturnValueOnce(collectionRefresh.promise)

  await wrapper.get('[aria-label="打开集合 物理"]').trigger('click')
  await wrapper.get('[data-testid="favorite-document-9"]').trigger('click')
  saving.resolve({ items: [{ document_id: 9, ok: true, code: null }] })
  await flushPromises()
  collectionRefresh.resolve([{
    ...store.knowledgeDocuments[0], display_name: '目标集合讲义.md', favorite: false, collection_ids: [4], tags: ['目标集合'],
  }])
  await flushPromises()

  expect(wrapper.get('.center-heading strong').text()).toBe('物理')
  expect(wrapper.get('[data-testid="document-grid"]').text()).toContain('目标集合讲义.md')
  expect(store.knowledgeDocuments[0].favorite).toBe(true)
  expect(wrapper.get('[data-testid="favorite-document-9"]').text()).toBe('★')
})

it('refreshes a pending favorite-only collection after unfavoriting on the old list', async () => {
  store.knowledgeCollections = [
    ...store.knowledgeCollections,
    { id: 4, name: '物理', description: '力与运动', color: '#8f9d7a', document_count: 2, bound_session_count: 0, created_at: '', updated_at: '' },
  ]
  store.knowledgeDocuments = [{
    ...store.knowledgeDocuments[0], favorite: true, deleted_at: null, collection_ids: [3, 4], tags: [],
  }]
  const staleCollectionRefresh = deferred<KnowledgeDocument[]>()
  const latestFavoriteRefresh = deferred<KnowledgeDocument[]>()
  const saving = deferred<{ items: { document_id: number; ok: boolean; code: null }[] }>()
  store.bulkKnowledgeDocuments.mockReturnValueOnce(saving.promise)
  const wrapper = mount(KnowledgeLibrary, { global: { stubs: { ElDrawer: { template: '<div><slot /></div>' } } } })
  await flushPromises()
  await wrapper.findAll('.advanced-filters input[type="checkbox"]')[1].setValue(true)
  await flushPromises()
  apiMock.knowledgeDocuments.mockClear()
  apiMock.knowledgeDocuments
    .mockReturnValueOnce(staleCollectionRefresh.promise)
    .mockReturnValueOnce(latestFavoriteRefresh.promise)

  await wrapper.get('[aria-label="打开集合 物理"]').trigger('click')
  await wrapper.get('[data-testid="favorite-document-9"]').trigger('click')
  saving.resolve({ items: [{ document_id: 9, ok: true, code: null }] })
  await flushPromises()

  expect(apiMock.knowledgeDocuments).toHaveBeenNthCalledWith(2, expect.objectContaining({
    collectionId: 4, favorite: true,
  }))
  staleCollectionRefresh.resolve([{
    ...store.knowledgeDocuments[0], id: 9, display_name: '已取消旧快照.md', favorite: true, collection_ids: [4],
  }])
  await flushPromises()
  expect(wrapper.get('[data-testid="document-grid"]').text()).not.toContain('已取消旧快照.md')

  latestFavoriteRefresh.resolve([{
    ...store.knowledgeDocuments[0], id: 10, display_name: '仍收藏资料.md', favorite: true, collection_ids: [4],
  }])
  await flushPromises()
  expect(wrapper.get('.center-heading strong').text()).toBe('物理')
  expect(wrapper.get('[data-testid="document-grid"]').text()).toContain('仍收藏资料.md')
  expect(wrapper.get('[data-testid="document-grid"]').text()).not.toContain('已取消旧快照.md')
})

it('does not report a stale filter failure after a newer filter succeeds', async () => {
  const wrapper = mount(KnowledgeLibrary, { global: { stubs: { ElDrawer: { template: '<div><slot /></div>' } } } })
  await flushPromises()
  const stale = deferred<KnowledgeDocument[]>()
  apiMock.knowledgeDocuments
    .mockReturnValueOnce(stale.promise)
    .mockResolvedValueOnce(store.knowledgeDocuments)

  await wrapper.get('[aria-label="筛选知识库资料"]').setValue('旧筛选')
  await wrapper.get('[aria-label="筛选知识库资料"]').setValue('新筛选')
  await flushPromises()
  stale.reject(new Error('旧筛选失败'))
  await flushPromises()

  expect(messageMock.error).not.toHaveBeenCalledWith('旧筛选失败')
})

it('loads only the first collection documents on a normal visit', async () => {
  store.knowledgeDocuments = [
    ...store.knowledgeDocuments,
    { id: 10, sha256: 'b'.repeat(64), display_name: '其他集合.md', extension: '.md', mime_type: 'text/markdown', byte_size: 2048, status: 'COMPLETED', page_count: null, slide_count: null, sheet_count: null, text_characters: 900, chunk_count: 2, parser_version: 'chunk-v1', safe_error_code: null, created_at: '', updated_at: '' },
  ]
  apiMock.knowledgeDocuments.mockResolvedValue([store.knowledgeDocuments[0]])

  const wrapper = mount(KnowledgeLibrary, { global: { stubs: { ElDrawer: { template: '<div><slot /></div>' } } } })
  await flushPromises()

  expect(apiMock.knowledgeDocuments).toHaveBeenCalledWith({
    collectionId: 3, trash: false, sort: 'created', direction: 'desc',
  })
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

it('toggles one favorite without changing selection or reloading the document list', async () => {
  store.knowledgeDocuments = [{
    ...store.knowledgeDocuments[0], favorite: false, deleted_at: null, collection_ids: [3], tags: [],
  }]
  store.bulkKnowledgeDocuments.mockResolvedValueOnce({
    items: [{ document_id: 9, ok: true, code: null }],
  })
  const wrapper = mount(KnowledgeLibrary, {
    global: { stubs: { ElDrawer: { template: '<div><slot /></div>' } } },
  })
  await flushPromises()
  apiMock.knowledgeDocuments.mockClear()

  await wrapper.get('[data-testid="favorite-document-9"]').trigger('click')

  expect(wrapper.get('[data-testid="bulk-selection-count"]').text()).toContain('0')
  expect(wrapper.get('[data-testid="favorite-document-9"]').text()).toBe('★')
  await flushPromises()

  expect(store.bulkKnowledgeDocuments).toHaveBeenCalledWith({
    action: 'favorite', document_ids: [9], collection_ids: [], tags: [], favorite: true,
  }, { refresh: false })
  expect(apiMock.knowledgeDocuments).not.toHaveBeenCalled()
})

it('keeps a pending favorite visible across a concurrent refresh and reconciles success onto refreshed fields', async () => {
  const saving = deferred<{ items: { document_id: number; ok: boolean; code: null }[] }>()
  store.knowledgeDocuments = [{
    ...store.knowledgeDocuments[0], favorite: false, deleted_at: null, collection_ids: [3], tags: [],
  }]
  store.bulkKnowledgeDocuments.mockReturnValueOnce(saving.promise)
  const wrapper = mount(KnowledgeLibrary, {
    global: { stubs: { ElDrawer: { template: '<div><slot /></div>' } } },
  })
  await flushPromises()

  await wrapper.get('[data-testid="favorite-document-9"]').trigger('click')
  store.knowledgeDocuments = [{ ...store.knowledgeDocuments[0], favorite: false, tags: ['刷新保留'] }]
  await nextTick()
  expect(wrapper.get('[data-testid="favorite-document-9"]').text()).toBe('★')

  saving.resolve({ items: [{ document_id: 9, ok: true, code: null }] })
  await flushPromises()

  expect(store.knowledgeDocuments[0].favorite).toBe(true)
  expect(store.knowledgeDocuments[0].tags).toEqual(['刷新保留'])
  expect(wrapper.get('[data-testid="favorite-document-9"]').text()).toBe('★')
})

it('ignores a stale document refresh that resolves after a favorite save succeeds', async () => {
  store.knowledgeDocuments = [{
    ...store.knowledgeDocuments[0], favorite: false, deleted_at: null, collection_ids: [3], tags: [],
  }]
  const staleRefresh = deferred<KnowledgeDocument[]>()
  const saving = deferred<{ items: { document_id: number; ok: boolean; code: null }[] }>()
  const wrapper = mount(KnowledgeLibrary, {
    global: { stubs: { ElDrawer: { template: '<div><slot /></div>' } } },
  })
  await flushPromises()
  apiMock.knowledgeDocuments.mockReturnValueOnce(staleRefresh.promise)
  store.bulkKnowledgeDocuments.mockReturnValueOnce(saving.promise)

  await wrapper.get('[aria-label="筛选知识库资料"]').setValue('旧请求')
  await wrapper.get('[data-testid="favorite-document-9"]').trigger('click')
  saving.resolve({ items: [{ document_id: 9, ok: true, code: null }] })
  await flushPromises()
  staleRefresh.resolve([{ ...store.knowledgeDocuments[0], favorite: false, tags: ['旧响应'] }])
  await flushPromises()

  expect(store.knowledgeDocuments[0].favorite).toBe(true)
  expect(store.knowledgeDocuments[0].tags).not.toEqual(['旧响应'])
})

it('applies a document refresh started after favorite begins without losing the saved favorite', async () => {
  store.knowledgeDocuments = [{
    ...store.knowledgeDocuments[0], favorite: false, deleted_at: null, collection_ids: [3], tags: [],
  }]
  const saving = deferred<{ items: { document_id: number; ok: boolean; code: null }[] }>()
  const refreshed = deferred<KnowledgeDocument[]>()
  store.bulkKnowledgeDocuments.mockReturnValueOnce(saving.promise)
  const wrapper = mount(KnowledgeLibrary, {
    global: { stubs: { ElDrawer: { template: '<div><slot /></div>' } } },
  })
  await flushPromises()
  apiMock.knowledgeDocuments.mockClear()
  apiMock.knowledgeDocuments.mockReturnValueOnce(refreshed.promise)

  await wrapper.get('[data-testid="favorite-document-9"]').trigger('click')
  await wrapper.get('[aria-label="筛选知识库资料"]').setValue('后发请求')
  expect(apiMock.knowledgeDocuments).toHaveBeenCalledOnce()

  saving.resolve({ items: [{ document_id: 9, ok: true, code: null }] })
  await flushPromises()
  refreshed.resolve([{ ...store.knowledgeDocuments[0], favorite: false, tags: ['后发响应'] }])
  await flushPromises()

  expect(store.knowledgeDocuments[0].tags).toEqual(['后发响应'])
  expect(store.knowledgeDocuments[0].favorite).toBe(true)
  expect(wrapper.get('[data-testid="favorite-document-9"]').text()).toBe('★')
})

it('applies the latest document refresh started before a favorite save that fails', async () => {
  store.knowledgeDocuments = [{
    ...store.knowledgeDocuments[0], favorite: false, deleted_at: null, collection_ids: [3], tags: [],
  }]
  const refreshed = deferred<KnowledgeDocument[]>()
  const saving = deferred<never>()
  store.bulkKnowledgeDocuments.mockReturnValueOnce(saving.promise)
  const wrapper = mount(KnowledgeLibrary, {
    global: { stubs: { ElDrawer: { template: '<div><slot /></div>' } } },
  })
  await flushPromises()
  apiMock.knowledgeDocuments.mockClear()
  apiMock.knowledgeDocuments.mockReturnValueOnce(refreshed.promise)

  await wrapper.get('[aria-label="筛选知识库资料"]').setValue('收藏前请求')
  expect(apiMock.knowledgeDocuments).toHaveBeenCalledOnce()
  await wrapper.get('[data-testid="favorite-document-9"]').trigger('click')
  saving.reject(new Error('收藏保存失败'))
  await flushPromises()
  refreshed.resolve([{ ...store.knowledgeDocuments[0], favorite: false, tags: ['失败后仍应用'] }])
  await flushPromises()

  expect(store.knowledgeDocuments[0].tags).toEqual(['失败后仍应用'])
  expect(store.knowledgeDocuments[0].favorite).toBe(false)
})

it('rolls back one favorite without disturbing selection when saving fails', async () => {
  store.knowledgeDocuments = [{
    ...store.knowledgeDocuments[0], favorite: false, deleted_at: null, collection_ids: [3], tags: [],
  }]
  const saving = deferred<never>()
  store.bulkKnowledgeDocuments.mockReturnValueOnce(saving.promise)
  const wrapper = mount(KnowledgeLibrary, {
    global: { stubs: { ElDrawer: { template: '<div><slot /></div>' } } },
  })
  await flushPromises()
  apiMock.knowledgeDocuments.mockClear()

  await wrapper.get('[data-testid="favorite-document-9"]').trigger('click')
  store.knowledgeDocuments = [{ ...store.knowledgeDocuments[0], favorite: true, tags: ['并发刷新'] }]
  saving.reject(new Error('收藏保存失败'))
  await flushPromises()

  expect(wrapper.get('[data-testid="bulk-selection-count"]').text()).toContain('0')
  expect(wrapper.get('[data-testid="favorite-document-9"]').text()).toBe('☆')
  expect(store.knowledgeDocuments[0].tags).toEqual(['并发刷新'])
  expect(apiMock.knowledgeDocuments).not.toHaveBeenCalled()
  expect(messageMock.error).toHaveBeenCalledWith('收藏保存失败')
})
