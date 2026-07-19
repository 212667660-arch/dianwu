import { flushPromises, mount } from '@vue/test-utils'
import { reactive } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, expect, it, vi } from 'vitest'
import { activateLocale, installLocaleMessages } from '@/i18n'

const demo = {
  session_id: 'demo_offline_v1', seeded: true, mode: 'offline' as const,
  degradation_message: '模型不可用：使用内置原创数据。',
  dataset: { title: '一次函数探究课', license: 'CC0-1.0', original: true, collection_id: 3 },
  agent_steps: [
    { agent: '画像 Agent', status: 'COMPLETED', detail: '画像完成' },
    { agent: '答案复核 Agent', status: 'COMPLETED', detail: '公式检查通过' },
  ],
  mastery_before: [{ name: '一次函数', score: 0.25 }],
  mastery_after: [{ name: '一次函数', score: 0.62 }],
  routes: { overview: '/dashboard', agents: '/agents', tutor: '/tutor' },
}

const store = reactive({
  loading: false, live: true, session: null as any, progress: null as any, nextAction: null as any,
  resources: [] as any[], demoSnapshot: null as typeof demo | null,
  refreshAll: vi.fn(), startDemo: vi.fn(async () => { store.demoSnapshot = demo }),
})
vi.mock('@/stores/backend', () => ({ useBackendStore: () => store }))

import Dashboard from './Dashboard.vue'

beforeEach(() => {
  vi.clearAllMocks()
  store.demoSnapshot = null
})

it('starts one-click demo and shows truthful offline agents and mastery comparison', async () => {
  const router = createRouter({ history: createMemoryHistory(), routes: [
    { path: '/dashboard', component: Dashboard }, { path: '/agents', component: { template: '<div />' } },
  ] })
  await router.push('/dashboard'); await router.isReady()
  const wrapper = mount(Dashboard, {
    global: { plugins: [router], stubs: { ElButton: { emits: ['click'], template: '<button @click="$emit(\'click\')"><slot /></button>' }, ElProgress: true, ElTag: true, ElIcon: true } },
  })

  await wrapper.get('[data-testid="start-demo"]').trigger('click')
  await flushPromises()

  expect(store.startDemo).toHaveBeenCalledWith(false)
  expect(wrapper.get('[data-testid="demo-showcase"]').text()).toContain('模型不可用')
  expect(wrapper.text()).toContain('CC0-1.0')
  expect(wrapper.text()).toContain('25% → 62%')
  expect(wrapper.text()).toContain('答案复核 Agent')
})

it('switches dashboard shell copy at runtime without translating demo content', async () => {
  installLocaleMessages('en-US', { views: { dashboard: { title: 'Learning overview', runDemo: 'Run demo' } } })
  activateLocale('en-US')
  store.demoSnapshot = demo
  const router = createRouter({ history: createMemoryHistory(), routes: [
    { path: '/dashboard', component: Dashboard }, { path: '/tutor', component: { template: '<div />' } },
  ] })
  await router.push('/dashboard'); await router.isReady()
  const wrapper = mount(Dashboard, {
    global: { plugins: [router], stubs: { ElButton: { template: '<button><slot /></button>' }, ElProgress: true, ElTag: true, ElIcon: true } },
  })

  expect(wrapper.text()).toContain('Learning overview')
  expect(wrapper.text()).toContain('Run demo')
  expect(wrapper.text()).toContain('一次函数探究课')
})
