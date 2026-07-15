import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import ConversationRail from './ConversationRail.vue'

describe('ConversationRail', () => {
  it('shows the active space and emits a new-session action', async () => {
    const wrapper = mount(ConversationRail, {
      props: { sessionLabel: '一次函数 · 第 2 次学习', activePath: '/tutor' },
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
  })
})
