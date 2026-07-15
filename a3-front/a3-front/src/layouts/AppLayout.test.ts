import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createRouter, createMemoryHistory } from 'vue-router'

const backendMock = vi.hoisted(() => ({
  live: true,
  ready: true,
  loading: false,
  sessionId: 'test-session',
  session: null,
  model: { api_key_configured: true },
  modelConfigured: true,
  progress: { knowledge_points: [] },
  nextAction: null,
  resources: [],
  setSessionId: vi.fn(),
  refreshAll: vi.fn(),
  lastError: '',
}))

vi.mock('@/stores/backend', () => ({ useBackendStore: () => backendMock }))
vi.mock('@/router', () => ({ routes: [{ path: '/', children: [] }] }))

import AppLayout from './AppLayout.vue'

function bridgeWithExit() {
  let listener: ((payload: { code: number | null }) => void) | undefined
  const unsubscribe = vi.fn()
  window.a3Desktop = {
    request: vi.fn(),
    modelConfigTest: vi.fn(),
    modelConfigSave: vi.fn(),
    startStream: vi.fn(),
    cancelStream: vi.fn(),
    onStreamEvent: vi.fn(() => () => {}),
    onBackendExit: vi.fn(next => { listener = next; return unsubscribe }),
  }
  return { emit: (payload: { code: number | null }) => listener?.(payload), unsubscribe }
}

const stubs = {
  RouterView: { template: '<div />' },
  RouterLink: { template: '<a><slot /></a>' },
  ElIcon: { template: '<i><slot /></i>' },
  ElProgress: { template: '<div />' },
  ElButton: { template: '<button><slot /></button>' },
  ElInput: { props: ['modelValue'], template: '<div />' },
  ElTooltip: { template: '<span><slot /></span>' },
  ElDrawer: { template: '<div><slot /></div>' },
}

beforeEach(() => {
  backendMock.live = true
  backendMock.ready = true
  backendMock.model = { api_key_configured: true }
  backendMock.modelConfigured = true
  backendMock.lastError = ''
  backendMock.refreshAll.mockReset().mockResolvedValue(undefined)
  delete window.a3Desktop
})

describe('AppLayout backend lifecycle', () => {
  it('marks the backend unavailable after a desktop backend exit without rendering runtime values', async () => {
    const { emit, unsubscribe } = bridgeWithExit()
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: AppLayout }] })
    await router.push('/')
    await router.isReady()
    const wrapper = mount(AppLayout, { global: { plugins: [router], stubs } })

    emit({ code: 1 })
    await flushPromises()

    expect(backendMock.live).toBe(false)
    expect(backendMock.ready).toBe(false)
    expect(backendMock.lastError).toContain('本地学习服务已停止')
    expect(wrapper.text()).not.toContain('127.0.0.1')
    expect(wrapper.text()).not.toContain('桌面令牌')
    wrapper.unmount()
    expect(unsubscribe).toHaveBeenCalledTimes(1)
  })

  it('routes an online unconfigured app to the dedicated model settings page', async () => {
    backendMock.model = { api_key_configured: false }
    backendMock.modelConfigured = false
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/dashboard', component: AppLayout },
        { path: '/model-settings', component: { template: '<div>settings</div>' } },
      ],
    })
    await router.push('/dashboard')
    await router.isReady()

    mount(AppLayout, { global: { plugins: [router], stubs } })
    await flushPromises()

    expect(router.currentRoute.value.path).toBe('/model-settings')
  })

  it('renders the companion workspace rail and desk panel', async () => {
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: AppLayout }] })
    await router.push('/')
    await router.isReady()
    const wrapper = mount(AppLayout, { global: { plugins: [router], stubs } })
    await flushPromises()
    expect(wrapper.find('[data-test="conversation-rail"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="desk-panel"]').exists()).toBe(true)
  })
})
