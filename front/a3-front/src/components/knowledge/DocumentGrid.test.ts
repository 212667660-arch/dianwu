import { mount } from '@vue/test-utils'
import { expect, it, vi } from 'vitest'
import DocumentGrid from './DocumentGrid.vue'

const document = { id: 9, sha256: 'a'.repeat(64), display_name: '极限讲义.pdf', extension: '.pdf', mime_type: 'application/pdf', byte_size: 1024, status: 'PARSING', page_count: null, slide_count: null, sheet_count: null, text_characters: 0, chunk_count: 0, parser_version: null, safe_error_code: null, created_at: '', updated_at: '' }
const job = { id: 7, document_id: 9, status: 'PARSING', progress: 42, stage: 'parsing', retryable: false, safe_error_code: null, cancel_requested: false, version: 1, created_at: '', updated_at: '' }

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
