import { mount } from '@vue/test-utils'
import { expect, it } from 'vitest'
import KnowledgeSourceList from './KnowledgeSourceList.vue'

const source = { reference_id: '资料1', document_id: 9, document_name: '极限讲义.pdf', locator_label: '第 3 页', locator: { type: 'page' as const, start: 3, end: 3 }, chunk_id: 11, retrieval_mode: 'keyword' as const }

it('emits a cited source without exposing a filesystem path', async () => {
  const wrapper = mount(KnowledgeSourceList, { props: { sources: [source] } })
  await wrapper.get('[aria-label="查看资料1：极限讲义.pdf 第3页"]').trigger('click')
  expect(wrapper.emitted('open')?.[0]).toEqual([source])
  expect(wrapper.text()).toContain('关键词')
  expect(wrapper.html()).not.toContain('objects/')
})
