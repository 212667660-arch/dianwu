import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import type { ModelProfilePolicy, ModelProfileSummary, SessionModelPreference } from '@/api'
import { activateLocale, installLocaleMessages } from '@/i18n'

import ModelSelectionPopover from './ModelSelectionPopover.vue'

const profiles: ModelProfileSummary[] = [
  {
    id: 'profile-a', label: '主连接', enabled: true, provider: 'openai', base_url: 'https://a.example.test',
    api_key_configured: true, anthropic_version: '2023-06-01', request_timeout_seconds: 60,
    default_model_id: 'model-a', models: [{ id: 'model-a', provider_model_name: 'model-a-provider', label: 'Model A', max_output_tokens: 4096, supported_reasoning_efforts: ['auto', 'low', 'medium', 'high'], reasoning_adapter: 'openai_reasoning_effort' }],
  },
  {
    id: 'profile-b', label: '轻量备用', enabled: true, provider: 'openai', base_url: 'https://b.example.test',
    api_key_configured: true, anthropic_version: '2023-06-01', request_timeout_seconds: 60,
    default_model_id: 'model-b', models: [{ id: 'model-b', provider_model_name: 'model-b-provider', label: 'Model B', max_output_tokens: 4096, supported_reasoning_efforts: ['auto', 'off'], reasoning_adapter: 'none' }],
  },
]
const policy: ModelProfilePolicy = { default_profile_id: 'profile-a', auto_failover: true, fallback_profile_ids: ['profile-b'] }
const preference: SessionModelPreference = {
  session_id: 'space-a', profile_mode: 'manual', preferred_profile_id: 'profile-a', model_id: 'model-a', reasoning_effort: 'xhigh', failover_override: 'inherit',
}

describe('ModelSelectionPopover', () => {
  it('shows the effective clamped effort and disables unsupported efforts after switching models', async () => {
    const wrapper = mount(ModelSelectionPopover, { props: { profiles, policy, preference, busy: false } })

    expect(wrapper.get('[data-testid="model-selection-trigger"]').text()).toContain('Model A')
    expect(wrapper.get('[data-testid="model-selection-trigger"]').text()).toContain('深入')
    await wrapper.get('[data-testid="model-selection-trigger"]').trigger('click')
    expect(wrapper.get('[data-testid="reasoning-xhigh"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('[data-testid="reasoning-high"]').attributes('disabled')).toBeUndefined()

    await wrapper.get('[data-testid="profile-selection"]').setValue('profile-b')
    expect(wrapper.get('[data-testid="reasoning-low"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('[data-testid="reasoning-off"]').attributes('disabled')).toBeUndefined()
  })

  it('emits an auto profile preference when following the global policy', async () => {
    const wrapper = mount(ModelSelectionPopover, { props: { profiles, policy, preference, busy: false } })
    await wrapper.get('[data-testid="model-selection-trigger"]').trigger('click')
    await wrapper.get('[data-testid="profile-selection"]').setValue('__auto__')
    await wrapper.get('[data-testid="model-selection-save"]').trigger('click')

    expect(wrapper.emitted('save')?.[0]).toEqual([{
      profile_mode: 'auto', preferred_profile_id: null, model_id: null,
      reasoning_effort: 'xhigh', failover_override: 'inherit',
    }])
  })

  it('renders injected English model labels without changing model labels', async () => {
    installLocaleMessages('en-US', { components: { modelSelection: { reasoning: 'Reasoning effort', reasoningTitle: 'How this space thinks' } } })
    activateLocale('en-US')
    const wrapper = mount(ModelSelectionPopover, { props: { profiles, policy, preference, busy: false } })
    await wrapper.get('[data-testid="model-selection-trigger"]').trigger('click')

    expect(wrapper.text()).toContain('How this space thinks')
    expect(wrapper.text()).toContain('Reasoning effort')
    expect(wrapper.text()).toContain('Model A')
  })
})
