import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createRouter, createMemoryHistory } from 'vue-router'

const apiMock = vi.hoisted(() => ({
  streamChat: vi.fn(), chat: vi.fn(), cancelGeneration: vi.fn(),
}))
const DesktopApiErrorMock = vi.hoisted(() => class DesktopApiError extends Error {
  readonly status: number
  readonly code: string

  constructor(status: number, code: string, message: string) {
    super(message)
    this.name = 'DesktopApiError'
    this.status = status
    this.code = code
  }
})
const storeMock = vi.hoisted(() => ({
  ready: true, modelConfigured: true, sessionId: 'test-session', session: null, progress: null, nextAction: null,
  refreshSession: vi.fn(),
}))

vi.mock('@/api', () => ({
  backendApi: apiMock,
  DesktopApiError: DesktopApiErrorMock,
  errorMessage: (error: unknown) => error instanceof Error ? error.message : '请求失败',
}))
vi.mock('@/stores/backend', () => ({ useBackendStore: () => storeMock }))
vi.mock('element-plus', () => ({ ElMessage: { error: vi.fn(), info: vi.fn() } }))

import SmartTutor from './SmartTutor.vue'

const stubs = {
  ElIcon: { template: '<i><slot /></i>' },
  ElInput: { props: ['modelValue'], emits: ['update:modelValue'], template: '<textarea :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />' },
  ElButton: { props: ['disabled'], emits: ['click'], template: '<button :disabled="disabled" @click="$emit(\'click\')"><slot /></button>' },
  ElSwitch: { template: '<input type="checkbox" />' },
}

describe('SmartTutor failure recovery', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    storeMock.modelConfigured = true
    storeMock.refreshSession.mockResolvedValue(undefined)
    apiMock.streamChat.mockImplementation(async (_sessionId, _message, onEvent) => {
      onEvent({ event: 'error', code: 'FIELD_REQUIRED', message: '模型输出缺少必填字段，请重试。' })
    })
  })

  it('keeps a streaming failure visible and restores the draft for retry', async () => {
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/tutor', component: SmartTutor }] })
    await router.push('/tutor')
    await router.isReady()
    const wrapper = mount(SmartTutor, { global: { plugins: [router], stubs } })
    const textarea = wrapper.get('textarea')
    await textarea.setValue('请帮助我学习一次函数')
    const buttons = wrapper.findAll('button')
    const send = buttons.find(button => button.text() === '发送')
    expect(send).toBeDefined()
    await send!.trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('本次请求未完成')
    expect(wrapper.text()).toContain('模型输出缺少必填字段，请重试。')
    const retry = wrapper.findAll('button').find(button => button.text() === '重新编辑')
    expect(retry).toBeDefined()
    await retry!.trigger('click')
    expect((wrapper.get('textarea').element as HTMLTextAreaElement).value).toBe('请帮助我学习一次函数')
  })

  it('treats desktop stream cancellation as cancellation and releases the generation', async () => {
    apiMock.cancelGeneration.mockResolvedValue({ cancelled: true })
    apiMock.streamChat.mockImplementation(async (_sessionId, _message, onEvent, signal) => {
      onEvent({ event: 'delta', generation_id: 'generation_1', content: '正在生成' })
      await new Promise((_, reject) => signal?.addEventListener('abort', () => {
        reject(new DesktopApiErrorMock(499, 'DESKTOP_STREAM_CANCELLED', '生成已取消。'))
      }, { once: true }))
    })
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/tutor', component: SmartTutor }] })
    await router.push('/tutor')
    await router.isReady()
    const wrapper = mount(SmartTutor, { global: { plugins: [router], stubs } })
    await wrapper.get('textarea').setValue('测试取消')
    const send = wrapper.findAll('button').find(button => button.text() === '发送')
    await send!.trigger('click')
    await flushPromises()
    const cancel = wrapper.findAll('button').find(button => button.text() === '取消')
    expect(cancel).toBeDefined()
    await cancel!.trigger('click')
    await flushPromises()

    expect(apiMock.cancelGeneration).toHaveBeenCalledWith('generation_1', 'test-session')
    expect(wrapper.text()).not.toContain('本次请求未完成')
    expect(wrapper.text()).not.toContain('桌面令牌')
  })

  it('disables model sending while credentials are not configured', async () => {
    storeMock.modelConfigured = false
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/tutor', component: SmartTutor }] })
    await router.push('/tutor')
    await router.isReady()
    const wrapper = mount(SmartTutor, { global: { plugins: [router], stubs } })
    await wrapper.get('textarea').setValue('不应发送')
    const send = wrapper.findAll('button').find(button => button.text() === '发送')

    expect(send).toBeDefined()
    expect(send!.attributes('disabled')).toBeDefined()
    await send!.trigger('click')
    expect(apiMock.streamChat).not.toHaveBeenCalled()
    expect(apiMock.chat).not.toHaveBeenCalled()
  })
})
