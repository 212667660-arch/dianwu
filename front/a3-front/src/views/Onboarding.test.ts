import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'

const apiMock = vi.hoisted(() => ({
  desktopState: vi.fn(),
  desktopInfo: vi.fn(),
  completeDesktopOnboarding: vi.fn(),
}))
vi.mock('@/api', () => ({ backendApi: apiMock }))

import Onboarding from './Onboarding.vue'

function routerFixture() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/onboarding', component: Onboarding },
      { path: '/dashboard', component: { template: '<div>dashboard</div>' } },
    ],
  })
}

beforeEach(() => {
  vi.clearAllMocks()
  apiMock.desktopState.mockResolvedValue({ version: 1, onboarding_completed: false, ai_paused: false })
  apiMock.desktopInfo.mockResolvedValue({
    app_version: '1.0.0', backend_ready: true, data_directory_ready: true,
    model_configured: false, ocr_available: true, update_status: 'offline_build',
  })
  apiMock.completeDesktopOnboarding.mockResolvedValue({ version: 1, onboarding_completed: true, ai_paused: false })
})

it('shows first-run checks and completes onboarding into the application', async () => {
  const router = routerFixture()
  await router.push('/onboarding')
  await router.isReady()
  const wrapper = mount(Onboarding, { global: { plugins: [router] } })
  await flushPromises()

  expect(wrapper.text()).toContain('1.0.0')
  expect(wrapper.text()).toContain('离线 OCR')
  await wrapper.get('[data-testid="complete-onboarding"]').trigger('click')
  await flushPromises()

  expect(apiMock.completeDesktopOnboarding).toHaveBeenCalledWith({ offlineDemo: false })
  expect(router.currentRoute.value.path).toBe('/dashboard')
})

it('can skip model setup and enter the offline demo path', async () => {
  const router = routerFixture()
  await router.push('/onboarding')
  await router.isReady()
  const wrapper = mount(Onboarding, { global: { plugins: [router] } })
  await flushPromises()

  await wrapper.get('[data-testid="offline-demo-onboarding"]').trigger('click')
  await flushPromises()

  expect(apiMock.completeDesktopOnboarding).toHaveBeenCalledWith({ offlineDemo: true })
  expect(router.currentRoute.value.fullPath).toContain('demo=offline')
})
