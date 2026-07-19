import { mount } from '@vue/test-utils'
import { expect, it } from 'vitest'
import type { TextbookCatalogItem } from '@/api'
import { activateLocale, installLocaleMessages } from '@/i18n'
import TextbookCatalog from './TextbookCatalog.vue'

const items: TextbookCatalogItem[] = [
  {
    source_id: 'pep-junior-math', publisher: '人民教育出版社', title: '人教版初中数学教材电子版目录',
    stage: '初中', grade: '七至九年级', semester: '全册', subject: '数学', edition: '人教版',
    official_url: 'https://jc.pep.com.cn/?filed=初中&subject=数学', access_mode: 'OFFICIAL_READER',
    license_note: '版权所有，仅打开出版社官方在线阅读页。', verified_at: '2026-07-17', download_url: null,
  },
  {
    source_id: 'pep-high-math', publisher: '人民教育出版社', title: '人教版高中数学教材电子版目录',
    stage: '高中', grade: '必修与选择性必修', semester: '全册', subject: '数学', edition: '人教 A/B 版',
    official_url: 'https://jc.pep.com.cn/?filed=高中&subject=数学', access_mode: 'OFFICIAL_READER',
    license_note: '版权所有，仅打开出版社官方在线阅读页。', verified_at: '2026-07-17', download_url: null,
  },
]

it('filters math catalogs by stage and labels official-reader access', async () => {
  const wrapper = mount(TextbookCatalog, { props: { items } })

  await wrapper.get('[aria-label="选择高中教材"]').trigger('click')

  expect(wrapper.text()).toContain('人教版高中数学教材电子版目录')
  expect(wrapper.text()).not.toContain('人教版初中数学教材电子版目录')
  expect(wrapper.text()).toContain('人教社官方在线阅读')
  expect(wrapper.text()).not.toContain('下载到知识库')
  await wrapper.get('[aria-label="在线阅读 人教版高中数学教材电子版目录"]').trigger('click')
  expect(wrapper.emitted('open')?.[0]).toEqual([items[1]])
})

it('renders the injected textbook catalog kicker', () => {
  installLocaleMessages('en-US', { components: { textbookCatalog: { officialTextbooks: 'Verified textbook catalog' } } })
  activateLocale('en-US')
  const wrapper = mount(TextbookCatalog, { props: { items } })

  expect(wrapper.text()).toContain('Verified textbook catalog')
})
