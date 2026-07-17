import { mount } from '@vue/test-utils'
import { expect, it } from 'vitest'
import DocumentInspector from './DocumentInspector.vue'

it('offers a clear local-reader preview action for completed documents', async () => {
  const document = { id: 7, sha256: 'b'.repeat(64), display_name: '教材.pdf', extension: '.pdf', mime_type: 'application/pdf', byte_size: 2048, status: 'COMPLETED', page_count: 12, slide_count: null, sheet_count: null, text_characters: 900, chunk_count: 8, parser_version: 'pdf-v1', safe_error_code: null, created_at: '', updated_at: '' }
  const wrapper = mount(DocumentInspector, { props: { document, desktopAvailable: true } })

  await wrapper.get('[aria-label="预览（本地阅读器） 教材.pdf"]').trigger('click')

  expect(wrapper.emitted('open')?.[0]).toEqual([7])
  expect(wrapper.text()).toContain('预览（本地阅读器）')
})

it('shows OCR guidance and safe document metadata', async () => {
  const document = { id: 9, sha256: 'a'.repeat(64), display_name: '扫描讲义.pdf', extension: '.pdf', mime_type: 'application/pdf', byte_size: 1024, status: 'OCR_REQUIRED', page_count: 3, slide_count: null, sheet_count: null, text_characters: 0, chunk_count: 0, parser_version: null, safe_error_code: 'KNOWLEDGE_OCR_PACK_REQUIRED', created_at: '', updated_at: '' }
  const wrapper = mount(DocumentInspector, { props: { document, desktopAvailable: true } })
  expect(wrapper.text()).toContain('需要本地 OCR')
  expect(wrapper.text()).toContain('3 页')
  expect(wrapper.html()).not.toContain(document.sha256)
  await wrapper.get('[aria-label="重新解析 扫描讲义.pdf"]').trigger('click')
  expect(wrapper.emitted('rebuild')?.[0]).toEqual([9])
})
