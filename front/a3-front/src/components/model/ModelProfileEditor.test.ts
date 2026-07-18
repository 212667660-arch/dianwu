import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { ModelProfileSummary } from '@/api'

const storeMock = vi.hoisted(() => ({
  modelProfileBusy: false,
  testModelProfile: vi.fn(),
  upsertModelProfile: vi.fn(),
}))

vi.mock('@/stores/backend', () => ({ useBackendStore: () => storeMock }))
vi.mock('@/api', async importOriginal => {
  const actual = await importOriginal<typeof import('@/api')>()
  return { ...actual, errorMessage: (error: unknown) => error instanceof Error ? error.message : '请求失败' }
})

import ModelProfileEditor from './ModelProfileEditor.vue'

const profile: ModelProfileSummary = {
  id: 'primary', label: '主模型', enabled: true, provider: 'openai', base_url: 'https://api.example.test/v1',
  api_key_configured: true, anthropic_version: '2023-06-01', request_timeout_seconds: 60,
  default_model_id: 'model-a', models: [{ id: 'model-a', provider_model_name: 'model-a', label: 'Model A', max_output_tokens: 4096, supported_reasoning_efforts: ['auto', 'off', 'high'], reasoning_adapter: 'openai_reasoning_effort' }],
}

const stubs = {
  ElInput: {
    inheritAttrs: false, props: ['modelValue'], emits: ['update:modelValue'],
    template: '<input v-bind="$attrs" :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />',
  },
  ElInputNumber: {
    inheritAttrs: false, props: ['modelValue'], emits: ['update:modelValue'],
    template: '<input v-bind="$attrs" type="number" :value="modelValue" @input="$emit(\'update:modelValue\', Number($event.target.value))" />',
  },
  ElSelect: {
    inheritAttrs: false, props: ['modelValue'], emits: ['update:modelValue'],
    template: '<select v-bind="$attrs" :value="modelValue" @change="$emit(\'update:modelValue\', $event.target.value)"><slot /></select>',
  },
  ElOption: { props: ['label', 'value'], template: '<option :value="value">{{ label }}</option>' },
  ElCheckboxGroup: { template: '<div><slot /></div>' },
  ElCheckbox: { inheritAttrs: false, props: ['value', 'label'], template: '<label><input v-bind="$attrs" type="checkbox" :value="value ?? label" />{{ value ?? label }}</label>' },
  ElButton: {
    inheritAttrs: false, props: ['disabled', 'loading'], emits: ['click'],
    template: '<button v-bind="$attrs" :disabled="disabled || loading" @click="$emit(\'click\')"><slot /></button>',
  },
  ElAlert: { props: ['title'], template: '<div>{{ title }}<slot /></div>' },
}

function mountEditor(value: ModelProfileSummary | null, seedProfile: ModelProfileSummary | null = null) {
  return mount(ModelProfileEditor, { props: { profile: value, seedProfile }, global: { stubs } })
}

describe('ModelProfileEditor', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    storeMock.modelProfileBusy = false
    storeMock.testModelProfile.mockResolvedValue({ provider: 'openai', model_name: 'model-a', status: 'connected', latency_ms: 18 })
    storeMock.upsertModelProfile.mockResolvedValue({})
  })

  it('requires a key for a new profile and validates stable profile/model ids', async () => {
    const wrapper = mountEditor(null)
    await wrapper.get('[data-testid="profile-id"]').setValue('bad id')
    await wrapper.get('[data-testid="profile-label"]').setValue('新配置')
    await wrapper.get('[data-testid="model-0-provider-name"]').setValue('model-a')
    await wrapper.get('[data-testid="profile-test"]').trigger('click')
    await flushPromises()

    expect(storeMock.testModelProfile).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('配置 ID')

    await wrapper.get('[data-testid="profile-id"]').setValue('new-profile')
    await wrapper.get('[data-testid="profile-test"]').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('API Key')
    expect(storeMock.testModelProfile).not.toHaveBeenCalled()
  })

  it('never hydrates an existing key and exposes only fixed adapters and reasoning efforts', () => {
    const wrapper = mountEditor(profile)
    expect((wrapper.get('[data-testid="profile-api-key"]').element as HTMLInputElement).value).toBe('')
    expect(wrapper.html()).not.toContain('test-secret-key')

    const adapters = wrapper.findAll('[data-testid="model-0-adapter"] option').map(option => option.attributes('value'))
    expect(adapters).toEqual(['none', 'openai_reasoning_effort', 'anthropic_thinking'])
    const efforts = wrapper.findAll('[data-testid^="model-0-effort-"]').map(input => input.attributes('value'))
    expect(efforts).toEqual(['auto', 'off', 'low', 'medium', 'high', 'xhigh'])
  })

  it('copies safe model metadata into a new draft without copying credentials', () => {
    const seed = { ...profile, id: 'primary-copy', label: '主模型 副本' }
    const wrapper = mountEditor(null, seed)

    expect((wrapper.get('[data-testid="profile-id"]').element as HTMLInputElement).value).toBe('primary-copy')
    expect((wrapper.get('[data-testid="profile-label"]').element as HTMLInputElement).value).toBe('主模型 副本')
    expect((wrapper.get('[data-testid="profile-api-key"]').element as HTMLInputElement).value).toBe('')
    expect(wrapper.text()).toContain('新配置必须输入密钥')
  })

  it('allows save only after testing the unchanged draft and clears the key after save', async () => {
    const wrapper = mountEditor(profile)
    await wrapper.get('[data-testid="profile-test"]').trigger('click')
    await flushPromises()

    expect(storeMock.testModelProfile).toHaveBeenCalledWith(expect.objectContaining({ id: 'primary', api_key: '' }))
    expect(wrapper.get('[data-testid="profile-save"]').attributes('disabled')).toBeUndefined()

    await wrapper.get('[data-testid="profile-api-key"]').setValue('replacement-secret')
    expect(wrapper.get('[data-testid="profile-save"]').attributes('disabled')).toBeDefined()
    await wrapper.get('[data-testid="profile-test"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-testid="profile-save"]').trigger('click')
    await flushPromises()

    expect(storeMock.upsertModelProfile).toHaveBeenCalledWith(expect.objectContaining({ api_key: 'replacement-secret' }))
    expect((wrapper.get('[data-testid="profile-api-key"]').element as HTMLInputElement).value).toBe('')
    expect(wrapper.emitted('saved')?.[0]).toEqual(['primary'])
  })

  it('clears a candidate key after test or save failure', async () => {
    storeMock.testModelProfile.mockRejectedValueOnce(new Error('认证失败'))
    const wrapper = mountEditor(profile)
    await wrapper.get('[data-testid="profile-api-key"]').setValue('bad-secret')
    await wrapper.get('[data-testid="profile-test"]').trigger('click')
    await flushPromises()
    expect((wrapper.get('[data-testid="profile-api-key"]').element as HTMLInputElement).value).toBe('')
    expect(wrapper.text()).toContain('认证失败')

    storeMock.upsertModelProfile.mockRejectedValueOnce(new Error('保存失败'))
    await wrapper.get('[data-testid="profile-api-key"]').setValue('next-secret')
    await wrapper.get('[data-testid="profile-test"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-testid="profile-save"]').trigger('click')
    await flushPromises()
    expect((wrapper.get('[data-testid="profile-api-key"]').element as HTMLInputElement).value).toBe('')
    expect(wrapper.text()).toContain('保存失败')
  })
})
