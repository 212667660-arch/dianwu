import { mount } from '@vue/test-utils'
import { expect, it } from 'vitest'
import { activateLocale, installLocaleMessages } from '@/i18n'
import CollectionRail from './CollectionRail.vue'

it('selects a collection with an accessible button', async () => {
  const wrapper = mount(CollectionRail, { props: { collections: [{ id: 3, name: '高数', description: '极限与导数', color: '#c98f65', document_count: 2, bound_session_count: 1, created_at: '', updated_at: '' }], selectedId: null } })
  await wrapper.get('[aria-label="打开集合 高数"]').trigger('click')
  expect(wrapper.emitted('select')?.[0]).toEqual([3])
})

it('offers rename and delete actions without nesting interactive controls', async () => {
  const collection = { id: 3, name: '高数', description: '', color: '#c98f65', document_count: 2, bound_session_count: 1, created_at: '', updated_at: '' }
  const wrapper = mount(CollectionRail, { props: { collections: [collection], selectedId: 3 } })
  await wrapper.get('[aria-label="重命名集合 高数"]').trigger('click')
  await wrapper.get('[aria-label="删除集合 高数"]').trigger('click')
  expect(wrapper.emitted('rename')?.[0]).toEqual([collection])
  expect(wrapper.emitted('delete')?.[0]).toEqual([collection])
  expect(wrapper.find('.collection-card button').exists()).toBe(false)
})

it('renders injected English knowledge labels without changing collection names', () => {
  installLocaleMessages('en-US', { components: { collectionRail: { gardenTitle: 'Resource garden', myCollectionsTitle: 'My collections' } } })
  activateLocale('en-US')
  const wrapper = mount(CollectionRail, { props: { collections: [{ id: 3, name: '高数', description: '', color: '#c98f65', document_count: 2, bound_session_count: 1, created_at: '', updated_at: '' }], selectedId: null } })

  expect(wrapper.text()).toContain('Resource garden')
  expect(wrapper.text()).toContain('My collections')
  expect(wrapper.text()).toContain('高数')
})
