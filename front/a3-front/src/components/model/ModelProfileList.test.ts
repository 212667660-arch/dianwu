import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { ModelProfilePolicy, ModelProfileSummary, ModelRuntimeStatus } from '@/api'

const confirmMock = vi.hoisted(() => vi.fn())
vi.mock('element-plus', () => ({ ElMessageBox: { confirm: confirmMock } }))

import ModelProfileList from './ModelProfileList.vue'

const profiles: ModelProfileSummary[] = [
  {
    id: 'primary', label: '主模型', enabled: true, provider: 'openai', base_url: 'https://api.example.test/v1',
    api_key_configured: true, anthropic_version: '2023-06-01', request_timeout_seconds: 60,
    default_model_id: 'model-a', models: [{ id: 'model-a', provider_model_name: 'model-a', label: 'Model A', max_output_tokens: 4096, supported_reasoning_efforts: ['auto', 'high'], reasoning_adapter: 'openai_reasoning_effort' }],
  },
  {
    id: 'backup-a', label: '备用甲', enabled: true, provider: 'anthropic', base_url: 'https://api.anthropic.test',
    api_key_configured: true, anthropic_version: '2023-06-01', request_timeout_seconds: 60,
    default_model_id: 'claude', models: [{ id: 'claude', provider_model_name: 'claude-test', label: 'Claude', max_output_tokens: 4096, supported_reasoning_efforts: ['auto', 'medium'], reasoning_adapter: 'anthropic_thinking' }],
  },
  {
    id: 'backup-b', label: '备用乙', enabled: false, provider: 'openai', base_url: 'https://backup.example.test/v1',
    api_key_configured: true, anthropic_version: '2023-06-01', request_timeout_seconds: 60,
    default_model_id: 'model-b', models: [{ id: 'model-b', provider_model_name: 'model-b', label: 'Model B', max_output_tokens: 4096, supported_reasoning_efforts: ['auto'], reasoning_adapter: 'none' }],
  },
]

const policy: ModelProfilePolicy = {
  default_profile_id: 'primary', auto_failover: true, fallback_profile_ids: ['backup-a', 'backup-b'],
}

const runtimeStatus: ModelRuntimeStatus = {
  ready: true, default_profile_id: 'primary', auto_failover: true, fallback_profile_ids: ['backup-a', 'backup-b'],
  profiles: [
    { profile_id: 'primary', enabled: true, needs_attention: false, circuit_state: 'closed', cooldown_until: 0, consecutive_failures: 0 },
    { profile_id: 'backup-a', enabled: true, needs_attention: true, circuit_state: 'open', cooldown_until: Date.now() / 1000 + 30, consecutive_failures: 3 },
    { profile_id: 'backup-b', enabled: false, needs_attention: false, circuit_state: 'closed', cooldown_until: 0, consecutive_failures: 0 },
  ],
}

describe('ModelProfileList', () => {
  beforeEach(() => {
    confirmMock.mockReset()
    confirmMock.mockResolvedValue('confirm')
  })

  it('emits safe profile actions, fallback ordering and a confirmed deletion', async () => {
    const wrapper = mount(ModelProfileList, {
      props: { profiles, policy, runtimeStatus, selectedId: 'primary', busy: false },
    })

    await wrapper.get('[data-testid="profile-card-backup-a"]').trigger('click')
    await wrapper.get('[data-testid="profile-default-backup-a"]').trigger('click')
    await wrapper.get('[data-testid="profile-toggle-backup-a"]').trigger('click')
    await wrapper.get('[data-testid="profile-test-backup-a"]').trigger('click')
    await wrapper.get('[data-testid="profile-duplicate-backup-a"]').trigger('click')
    await wrapper.get('[data-testid="profile-move-down-backup-a"]').trigger('click')
    await wrapper.get('[data-testid="profile-delete-backup-a"]').trigger('click')

    expect(wrapper.emitted('select')?.[0]).toEqual([profiles[1]])
    expect(wrapper.emitted('set-default')?.[0]).toEqual(['backup-a'])
    expect(wrapper.emitted('toggle-enabled')?.[0]).toEqual([{ profileId: 'backup-a', enabled: false }])
    expect(wrapper.emitted('test')?.[0]).toEqual([profiles[1]])
    expect(wrapper.emitted('duplicate')?.[0]).toEqual([profiles[1]])
    expect(wrapper.emitted('move-fallback')?.[0]).toEqual([{ profileId: 'backup-a', direction: 1 }])
    expect(confirmMock).toHaveBeenCalledOnce()
    expect(wrapper.emitted('delete')?.[0]).toEqual(['backup-a'])
  })

  it('shows default, disabled and unhealthy states without rendering a full key', () => {
    const wrapper = mount(ModelProfileList, {
      props: { profiles, policy, runtimeStatus, selectedId: 'primary', busy: false },
    })

    expect(wrapper.get('[data-testid="profile-card-primary"]').classes()).toContain('is-selected')
    expect(wrapper.get('[data-testid="profile-card-primary"]').text()).toContain('默认')
    expect(wrapper.get('[data-testid="profile-toggle-primary"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('[data-testid="profile-card-backup-a"]').text()).toContain('需要处理')
    expect(wrapper.get('[data-testid="profile-card-backup-a"]').text()).toContain('冷却中')
    expect(wrapper.get('[data-testid="profile-card-backup-b"]').text()).toContain('已停用')
    expect(wrapper.html()).not.toContain('api_key')
    expect(wrapper.html()).not.toContain('test-secret-key')
  })
})
