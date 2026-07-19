import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, expect, it, vi } from 'vitest'
import { BUILT_IN_MESSAGES } from '@/i18n/catalog'
import { i18n, resetLocaleRuntimeForTests } from '@/i18n'

const apiMock = vi.hoisted(() => ({
  desktopInfo: vi.fn(), desktopDiagnostics: vi.fn(), exportDesktopDiagnostics: vi.fn(), checkDesktopUpdates: vi.fn(),
}))
vi.mock('@/api', () => ({ backendApi: apiMock }))
vi.mock('@/components/pet/PetSettingsCard.vue', () => ({ default: { template: '<div data-testid="pet-settings">pet</div>' } }))

import DesktopSettings from './DesktopSettings.vue'

beforeEach(() => {
  localStorage.clear()
  resetLocaleRuntimeForTests()
  vi.clearAllMocks()
  apiMock.desktopInfo.mockResolvedValue({ app_version: '1.2.3', backend_protocol: 'a3-desktop-api/v1', backend_ready: true, data_directory_ready: true, model_configured: true, ocr_available: true, ocr_version: '1.2.3', update_status: 'offline_build' })
  apiMock.desktopDiagnostics.mockResolvedValue({ app_version: '1.2.3', platform: 'win32', backend_ready: true, ocr_available: true, logs: ['backend ready'] })
  apiMock.exportDesktopDiagnostics.mockResolvedValue({ exported: true, file_name: 'report.json' })
  apiMock.checkDesktopUpdates.mockResolvedValue({ status: 'offline_build', message: '当前安装包未配置签名发布源，不会自动下载更新。' })
})

it('shows three bundled languages and activates the selected locale immediately', async () => {
  const wrapper = mount(DesktopSettings)
  await flushPromises()

  expect(wrapper.text()).toContain('English (United States)')
  expect(wrapper.text()).toContain('繁體中文（台灣）')
  await wrapper.get('[data-testid="language-activate-en-US"]').trigger('click')

  expect(i18n.global.locale.value).toBe('en-US')
  expect(localStorage.getItem('a3.ui-locale')).toBe('en-US')
  expect(wrapper.text()).toContain('Desktop settings')
})

it('shows version status and provides diagnosis log export and update checks', async () => {
  const wrapper = mount(DesktopSettings)
  await flushPromises()

  expect(wrapper.text()).toContain('1.2.3')
  expect(wrapper.text()).toContain('a3-desktop-api/v1')
  await wrapper.get('[data-testid="run-desktop-diagnostics"]').trigger('click')
  await wrapper.get('[data-testid="export-desktop-diagnostics"]').trigger('click')
  await wrapper.get('[data-testid="check-desktop-updates"]').trigger('click')
  await flushPromises()

  expect(wrapper.text()).toContain('backend ready')
  expect(wrapper.text()).toContain('report.json')
  expect(wrapper.text()).toContain('离线构建')
  expect(wrapper.text()).toContain('简体中文')
  expect(wrapper.text()).toContain(BUILT_IN_MESSAGES.views.desktopSettings.language.contentFollowsUi)
  expect(wrapper.find('[data-testid="pet-settings"]').exists()).toBe(true)
})
