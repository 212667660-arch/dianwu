import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'

const storeMock = vi.hoisted(() => ({
  model: {
    provider: 'openai',
    base_url: 'https://api.example.test',
    model_name: 'test-model',
    api_key_configured: false,
    api_key_hint: '',
    anthropic_version: '2023-06-01',
    request_timeout_seconds: 60,
  },
  modelConfigured: false,
  modelConfigBusy: false,
  testModelSettings: vi.fn(),
  saveModelSettings: vi.fn(),
}))

vi.mock('@/stores/backend', () => ({ useBackendStore: () => storeMock }))
vi.mock('@/api', () => ({
  errorMessage: (error: unknown) => error instanceof Error ? error.message : '请求失败',
}))

import ModelSettings from './ModelSettings.vue'

const stubs = {
  ElIcon: { template: '<i><slot /></i>' },
  ElForm: { template: '<form><slot /></form>' },
  ElFormItem: { template: '<label><slot /></label>' },
  ElInput: {
    inheritAttrs: false,
    props: ['modelValue'],
    emits: ['update:modelValue'],
    template: '<input v-bind="$attrs" :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />',
  },
  ElInputNumber: {
    inheritAttrs: false,
    props: ['modelValue'],
    emits: ['update:modelValue'],
    template: '<input v-bind="$attrs" type="number" :value="modelValue" @input="$emit(\'update:modelValue\', Number($event.target.value))" />',
  },
  ElSelect: {
    inheritAttrs: false,
    props: ['modelValue'],
    emits: ['update:modelValue'],
    template: '<select v-bind="$attrs" :value="modelValue" @change="$emit(\'update:modelValue\', $event.target.value)"><slot /></select>',
  },
  ElOption: { props: ['label', 'value'], template: '<option :value="value">{{ label }}</option>' },
  ElButton: {
    inheritAttrs: false,
    props: ['disabled', 'loading'],
    emits: ['click'],
    template: '<button v-bind="$attrs" :disabled="disabled || loading" @click="$emit(\'click\')"><slot /></button>',
  },
  ElAlert: { props: ['title'], template: '<div>{{ title }}<slot /></div>' },
}

function routerForTest() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/model-settings', component: ModelSettings },
      { path: '/tutor', component: { template: '<div>tutor</div>' } },
    ],
  })
}

describe('ModelSettings', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    storeMock.modelConfigured = false
    storeMock.model.api_key_configured = false
    storeMock.model.api_key_hint = ''
    storeMock.testModelSettings.mockResolvedValue({
      provider: 'openai', model_name: 'test-model', status: 'connected', latency_ms: 12,
    })
    storeMock.saveModelSettings.mockImplementation(async input => {
      storeMock.modelConfigured = true
      storeMock.model.api_key_configured = true
      storeMock.model.api_key_hint = 'test...-key'
      return { ...storeMock.model, model_name: input.model_name }
    })
  })

  it('tests then saves a first-run model config and clears the API Key', async () => {
    const router = routerForTest()
    await router.push('/model-settings')
    await router.isReady()
    const wrapper = mount(ModelSettings, { global: { plugins: [router], stubs } })
    const apiKey = wrapper.get('[data-testid="model-api-key"]')
    await apiKey.setValue('test-secret-key')

    await wrapper.get('[data-testid="model-test"]').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('连接成功')
    expect(wrapper.get('[data-testid="model-save"]').attributes('disabled')).toBeUndefined()

    await wrapper.get('[data-testid="model-save"]').trigger('click')
    await flushPromises()

    expect(storeMock.testModelSettings).toHaveBeenCalledTimes(1)
    expect(storeMock.saveModelSettings).toHaveBeenCalledTimes(1)
    expect((apiKey.element as HTMLInputElement).value).toBe('')
    expect(router.currentRoute.value.path).toBe('/tutor')
    expect(wrapper.text()).not.toContain('test-secret-key')
  })

  it('clears a failed candidate Key and keeps save disabled', async () => {
    storeMock.testModelSettings.mockRejectedValue(new Error('认证失败。'))
    const router = routerForTest()
    await router.push('/model-settings')
    await router.isReady()
    const wrapper = mount(ModelSettings, { global: { plugins: [router], stubs } })
    const apiKey = wrapper.get('[data-testid="model-api-key"]')
    await apiKey.setValue('bad-secret-key')

    await wrapper.get('[data-testid="model-test"]').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('认证失败。')
    expect((apiKey.element as HTMLInputElement).value).toBe('')
    expect(wrapper.get('[data-testid="model-save"]').attributes('disabled')).toBeDefined()
  })

  it('keeps save disabled when the form changes while a connection test is pending', async () => {
    let resolveTest: ((value: {
      provider: 'openai'
      model_name: string
      status: 'connected'
      latency_ms: number
    }) => void) | undefined
    storeMock.testModelSettings.mockImplementation(() => new Promise(resolve => {
      resolveTest = resolve
    }))
    const router = routerForTest()
    await router.push('/model-settings')
    await router.isReady()
    const wrapper = mount(ModelSettings, { global: { plugins: [router], stubs } })
    await wrapper.get('[data-testid="model-api-key"]').setValue('test-secret-key')

    await wrapper.get('[data-testid="model-test"]').trigger('click')
    await wrapper.get('[data-testid="model-name"]').setValue('changed-after-test-start')
    resolveTest?.({
      provider: 'openai',
      model_name: 'test-model',
      status: 'connected',
      latency_ms: 12,
    })
    await flushPromises()

    expect(wrapper.get('[data-testid="model-save"]').attributes('disabled')).toBeDefined()
  })
})
