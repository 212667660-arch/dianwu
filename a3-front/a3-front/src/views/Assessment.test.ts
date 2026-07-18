import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, expect, it, vi } from 'vitest'

const router = vi.hoisted(() => ({ push: vi.fn() }))
const store = vi.hoisted(() => ({
  resources: [{
    id: 1,
    topic: '一次函数',
    quality_score: 100,
    questions: [{
      id: 7,
      ordinal: 1,
      difficulty: '基础',
      prompt: '当 y=2x+1 且 x=2 时，y 等于多少？',
    }],
  }],
  reviews: [],
  mistakes: [],
  refreshSession: vi.fn(),
  submitAnswer: vi.fn().mockResolvedValue({
    correct: true,
    expected_answer: '5',
    explanation: '将 x=2 代入 y=2x+1。',
    feedback: '回答正确',
    error_type: null,
    mastery_score: 0.8,
    mastery_label: 'PROFICIENT',
    next_review_at: '',
  }),
}))

vi.mock('vue-router', () => ({ useRouter: () => router }))
vi.mock('@/stores/backend', () => ({ useBackendStore: () => store }))
vi.mock('element-plus', () => ({ ElMessage: { warning: vi.fn(), error: vi.fn(), success: vi.fn() } }))

import Assessment from './Assessment.vue'

const stubs = {
  ElInput: {
    props: ['modelValue'],
    emits: ['update:modelValue'],
    template: '<input :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)">',
  },
  ElInputNumber: { template: '<input class="el-input-number" type="number">' },
  ElButton: { template: '<button><slot /></button>' },
  ElTag: { template: '<span><slot /></span>' },
}

beforeEach(() => vi.clearAllMocks())

it('uses one answer field and submits without a manual hint counter', async () => {
  const wrapper = mount(Assessment, { global: { stubs } })

  const answer = wrapper.get('[data-testid="assessment-answer-7"]')
  await answer.setValue('5')

  expect(wrapper.find('.el-input-number').exists()).toBe(false)
  expect(wrapper.get('[data-testid="assessment-submit-7"]').isVisible()).toBe(true)

  await wrapper.get('[data-testid="assessment-submit-7"]').trigger('click')
  await flushPromises()

  expect(store.submitAnswer).toHaveBeenCalledWith(7, '5', 0)
})
