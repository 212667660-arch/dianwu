import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { activateLocale, installLocaleMessages } from '@/i18n'
import ConversationRail from './ConversationRail.vue'

describe('ConversationRail', () => {
  it('shows the active space and emits a new-session action', async () => {
    const wrapper = mount(ConversationRail, {
      props: { sessionLabel: '一次函数 · 第 2 次学习', sessionId: 'session-old', activePath: '/tutor' },
      global: {
        stubs: {
          RouterLink: { template: '<a><slot /></a>' },
          ElIcon: { template: '<i><slot /></i>' },
          ElButton: { emits: ['click'], template: '<button @click="$emit(\'click\')"><slot /></button>' },
        },
      },
    })
    expect(wrapper.text()).toContain('一次函数 · 第 2 次学习')
    await wrapper.get('[aria-label="新学习会话"]').trigger('click')
    expect(wrapper.emitted('new-session')).toHaveLength(1)
    expect(wrapper.text()).toContain('模型设置')
    await wrapper.get('[aria-label="会话 ID"]').setValue('session-new')
    await wrapper.get('[aria-label="切换会话"]').trigger('click')
    expect(wrapper.emitted('switch-session')?.[0]).toEqual(['session-new'])
  })

  it('renders injected English workspace labels without changing the session label', () => {
    installLocaleMessages('en-US', { components: { conversationRail: { conversation: 'Conversations', recent: 'Recently visited' } } })
    activateLocale('en-US')
    const wrapper = mount(ConversationRail, {
      props: { sessionLabel: '一次函数 · 第 2 次学习', sessionId: 'session-old', activePath: '/tutor' },
      global: { stubs: { RouterLink: { template: '<a><slot /></a>' }, ElIcon: { template: '<i><slot /></i>' }, ElButton: { template: '<button><slot /></button>' } } },
    })

    expect(wrapper.text()).toContain('Conversations')
    expect(wrapper.text()).toContain('Recently visited')
    expect(wrapper.text()).toContain('一次函数 · 第 2 次学习')
  })
})
