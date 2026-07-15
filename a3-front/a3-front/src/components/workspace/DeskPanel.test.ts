import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it } from 'vitest'
import DeskPanel from './DeskPanel.vue'
import type { NextAction } from '@/api'

const nextAction: NextAction = {
  session_id: 'demo',
  action: 'START_PRACTICE',
  knowledge_point_id: 1,
  knowledge_point: '一次函数',
  recommended_difficulty: '基础',
  reason: '先做一道热身题',
  due_at: null,
  suggested_request: '给我一道一次函数热身题',
}

describe('DeskPanel', () => {
  beforeEach(() => localStorage.clear())

  it('emits note changes and a suggested prompt', async () => {
    const wrapper = mount(DeskPanel, {
      props: { nextAction, mastery: 0.6, resourceCount: 1, note: '' },
      global: {
        stubs: {
          ElButton: { template: '<button v-bind="$attrs" @click="$emit(\'click\')"><slot /></button>' },
          ElProgress: true,
          ElIcon: { template: '<i><slot /></i>' },
        },
      },
    })
    const note = wrapper.get('textarea')
    await note.setValue('今晚复习斜率')
    expect(wrapper.emitted('update:note')?.at(-1)).toEqual(['今晚复习斜率'])
    await wrapper.get('[data-test="suggested-action"]').trigger('click')
    expect(wrapper.emitted('use-suggestion')?.[0]).toEqual(['给我一道一次函数热身题'])
  })
})
