import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const storeMock = vi.hoisted(() => ({
  modelProfiles: [] as any[],
  modelPolicy: null as any,
  modelRuntimeStatus: null as any,
  modelProfileBusy: false,
  lastError: '',
  refreshModelProfiles: vi.fn(),
  testModelProfile: vi.fn(),
  deleteModelProfile: vi.fn(),
  saveModelPolicy: vi.fn(),
}))

vi.mock('@/stores/backend', () => ({ useBackendStore: () => storeMock }))
vi.mock('@/api', () => ({ errorMessage: (error: unknown) => error instanceof Error ? error.message : '请求失败' }))

import ModelSettings from './ModelSettings.vue'

const primary = {
  id: 'primary', label: '主模型', enabled: true, provider: 'openai', base_url: 'https://api.example.test/v1',
  api_key_configured: true, anthropic_version: '2023-06-01', request_timeout_seconds: 60,
  default_model_id: 'model-a', models: [{ id: 'model-a', provider_model_name: 'model-a', label: 'Model A', max_output_tokens: 4096, supported_reasoning_efforts: ['auto'], reasoning_adapter: 'none' }],
}
const backup = { ...primary, id: 'backup', label: '备用模型', default_model_id: 'model-b', models: [{ ...primary.models[0], id: 'model-b', provider_model_name: 'model-b', label: 'Model B' }] }

const stubs = {
  ModelProfileList: {
    props: ['profiles', 'policy', 'runtimeStatus', 'selectedId', 'busy'],
    emits: ['select', 'create', 'duplicate', 'set-default', 'toggle-enabled', 'test', 'delete', 'move-fallback'],
    template: '<div data-testid="profile-list"><button data-testid="select-backup" @click="$emit(\'select\', profiles[1])">select</button><button data-testid="create-profile" @click="$emit(\'create\')">create</button><button data-testid="duplicate-backup" @click="$emit(\'duplicate\', profiles[1])">duplicate</button><button data-testid="default-backup" @click="$emit(\'set-default\', \'backup\')">default</button><button data-testid="move-backup" @click="$emit(\'move-fallback\', { profileId: \'backup\', direction: -1 })">move</button></div>',
  },
  ModelProfileEditor: {
    props: ['profile', 'seedProfile'], emits: ['saved'],
    template: '<div data-testid="profile-editor">{{ profile?.id || seedProfile?.id || "new" }}</div>',
  },
  ElSwitch: {
    inheritAttrs: false, props: ['modelValue', 'disabled'], emits: ['update:modelValue', 'change'],
    template: '<input v-bind="$attrs" type="checkbox" :checked="modelValue" :disabled="disabled" @change="$emit(\'update:modelValue\', $event.target.checked); $emit(\'change\', $event.target.checked)" />',
  },
  ElAlert: { props: ['title'], template: '<div>{{ title }}</div>' },
}

describe('ModelSettings', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    storeMock.modelProfiles = [primary, backup]
    storeMock.modelPolicy = { default_profile_id: 'primary', auto_failover: true, fallback_profile_ids: ['backup'] }
    storeMock.modelRuntimeStatus = { ready: true, default_profile_id: 'primary', auto_failover: true, fallback_profile_ids: ['backup'], profiles: [] }
    storeMock.modelProfileBusy = false
    storeMock.lastError = ''
    storeMock.refreshModelProfiles.mockResolvedValue(undefined)
    storeMock.testModelProfile.mockResolvedValue({ latency_ms: 12 })
    storeMock.deleteModelProfile.mockResolvedValue({})
    storeMock.saveModelPolicy.mockResolvedValue({})
  })

  it('refreshes profiles and selects the global default without exposing secrets', async () => {
    const wrapper = mount(ModelSettings, { global: { stubs } })
    await flushPromises()

    expect(storeMock.refreshModelProfiles).toHaveBeenCalledOnce()
    expect(wrapper.get('[data-testid="profile-editor"]').text()).toBe('primary')
    expect(wrapper.text()).toContain('自动使用备用配置')
    expect(wrapper.html()).not.toContain('api_key')
    expect(wrapper.html()).not.toContain('test-secret-key')
  })

  it('switches the editor between an existing profile and a clean new draft', async () => {
    const wrapper = mount(ModelSettings, { global: { stubs } })
    await flushPromises()
    await wrapper.get('[data-testid="select-backup"]').trigger('click')
    expect(wrapper.get('[data-testid="profile-editor"]').text()).toBe('backup')
    await wrapper.get('[data-testid="create-profile"]').trigger('click')
    expect(wrapper.get('[data-testid="profile-editor"]').text()).toBe('new')
    await wrapper.get('[data-testid="duplicate-backup"]').trigger('click')
    expect(wrapper.get('[data-testid="profile-editor"]').text()).toBe('backup-copy')
  })

  it('saves the failover switch, default profile and ordered fallback policy', async () => {
    const wrapper = mount(ModelSettings, { global: { stubs } })
    await flushPromises()

    await wrapper.get('[data-testid="auto-failover"]').setValue(false)
    await wrapper.get('[data-testid="default-backup"]').trigger('click')
    await wrapper.get('[data-testid="move-backup"]').trigger('click')
    await flushPromises()

    expect(storeMock.saveModelPolicy).toHaveBeenNthCalledWith(1, { default_profile_id: 'primary', auto_failover: false, fallback_profile_ids: ['backup'] })
    expect(storeMock.saveModelPolicy).toHaveBeenNthCalledWith(2, { default_profile_id: 'backup', auto_failover: true, fallback_profile_ids: ['primary'] })
  })

  it('shows a warm first-run invitation when no profile exists', async () => {
    storeMock.modelProfiles = []
    storeMock.modelPolicy = { default_profile_id: null, auto_failover: false, fallback_profile_ids: [] }
    const wrapper = mount(ModelSettings, { global: { stubs } })
    await flushPromises()
    expect(wrapper.text()).toContain('第一盏模型灯')
    expect(wrapper.get('[data-testid="profile-editor"]').text()).toBe('new')
  })
})
