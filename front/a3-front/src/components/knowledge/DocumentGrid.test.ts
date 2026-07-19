import { mount } from '@vue/test-utils'
import { expect, it, vi } from 'vitest'
import type { KnowledgeImportJob } from '@/api/types'
import DocumentGrid from './DocumentGrid.vue'

const document = { id: 9, sha256: 'a'.repeat(64), display_name: '极限讲义.pdf', extension: '.pdf', mime_type: 'application/pdf', byte_size: 1024, status: 'PARSING', page_count: null, slide_count: null, sheet_count: null, text_characters: 0, chunk_count: 0, parser_version: null, safe_error_code: null, created_at: '', updated_at: '' }
const job: KnowledgeImportJob = { id: 7, document_id: 9, status: 'PARSING', progress: 42, stage: 'parsing', retryable: false, safe_error_code: null, cancel_requested: false, current_page: null, page_count: null, eta_seconds: null, failed_pages: [], version: 1, created_at: '', updated_at: '' }

it('shows accessible progress and cancels the matching import', async () => {
  const cancel = vi.fn()
  const wrapper = mount(DocumentGrid, { props: { documents: [document], jobs: [job], selectedId: null, cancelJob: cancel } })
  expect(wrapper.get('[role="progressbar"]').attributes('aria-valuenow')).toBe('42')
  await wrapper.get('[aria-label="取消 极限讲义.pdf 的导入"]').trigger('click')
  expect(cancel).toHaveBeenCalledWith(7)
})

it('supports keyboard selection without rendering local paths', async () => {
  const wrapper = mount(DocumentGrid, { props: { documents: [document], jobs: [], selectedId: null, cancelJob: vi.fn() } })
  await wrapper.get('[aria-label="查看文档 极限讲义.pdf"]').trigger('keydown', { key: 'Enter' })
  expect(wrapper.emitted('select')?.[0]).toEqual([9])
  expect(wrapper.html()).not.toContain('object_relpath')
  expect(wrapper.html()).not.toContain('C:\\')
})

it('shows OCR page progress, ETA and retries only failed pages', async () => {
  const retry = vi.fn()
  const failedJob: KnowledgeImportJob = {
    ...job,
    status: 'FAILED',
    progress: 60,
    stage: 'ocr_partial',
    retryable: true,
    safe_error_code: 'KNOWLEDGE_OCR_PAGE_FAILED',
    current_page: 2,
    page_count: 5,
    eta_seconds: 8,
    failed_pages: [2, 5],
  }
  const wrapper = mount(DocumentGrid, {
    props: {
      documents: [{ ...document, status: 'FAILED' }],
      jobs: [failedJob],
      selectedId: null,
      cancelJob: vi.fn(),
      retryJob: retry,
    },
  })

  expect(wrapper.text()).toContain('第 2/5 页')
  expect(wrapper.text()).toContain('约 8 秒')
  expect(wrapper.text()).toContain('失败页：2、5')
  await wrapper.get('[aria-label="重试 极限讲义.pdf 的失败 OCR 页面"]').trigger('click')
  expect(retry).toHaveBeenCalledWith(7)
})

it('supports document selection and exposes favorite, tags, ETA and safe failure reason', async () => {
  const wrapper = mount(DocumentGrid, {
    props: {
      documents: [{ ...document, favorite: true, deleted_at: null, collection_ids: [3], tags: ['函数', '重点'] }],
      jobs: [{ ...job, current_page: 2, page_count: 8, eta_seconds: 12, safe_error_code: 'KNOWLEDGE_OCR_PAGE_FAILED' }],
      selectedId: null,
      selectedIds: [9],
      cancelJob: vi.fn(),
    },
  })

  expect(wrapper.get('[data-testid="document-checkbox-9"]').attributes('aria-checked')).toBe('true')
  expect(wrapper.text()).toContain('函数')
  expect(wrapper.text()).toContain('重点')
  expect(wrapper.text()).toContain('12')
  await wrapper.get('[data-testid="document-checkbox-9"]').trigger('click')
  await wrapper.get('[data-testid="favorite-document-9"]').trigger('click')
  expect(wrapper.emitted('toggle-selection')?.[0]).toEqual([9])
  expect(wrapper.emitted('toggle-favorite')?.[0]).toEqual([9, false])
})

it('disables only the favorite control whose update is pending', () => {
  const wrapper = mount(DocumentGrid, {
    props: {
      documents: [
        { ...document, favorite: false },
        { ...document, id: 10, display_name: '导数讲义.pdf', favorite: false },
      ],
      jobs: [],
      selectedId: null,
      cancelJob: vi.fn(),
      favoritePendingIds: [9],
    },
  })

  expect(wrapper.get('[data-testid="favorite-document-9"]').attributes('disabled')).toBeDefined()
  expect(wrapper.get('[data-testid="favorite-document-9"]').attributes('aria-busy')).toBe('true')
  expect(wrapper.get('[data-testid="favorite-document-10"]').attributes('disabled')).toBeUndefined()
})
