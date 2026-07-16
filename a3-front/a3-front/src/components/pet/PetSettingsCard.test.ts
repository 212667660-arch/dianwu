import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMock = vi.hoisted(() => ({
  pet: vi.fn(),
  updatePetSettings: vi.fn(),
}))
vi.mock('@/api', () => ({ backendApi: apiMock }))

import PetSettingsCard from './PetSettingsCard.vue'

describe('PetSettingsCard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiMock.pet.mockResolvedValue({
      available: true,
      pet: { id: 'motuan', displayName: '墨团', description: '学习伙伴' },
      settings: { visible: true, scale: 1, speed: 1 },
      state: 'idle',
    })
    apiMock.updatePetSettings.mockImplementation(async patch => ({
      available: true,
      pet: { id: 'motuan', displayName: '墨团', description: '学习伙伴' },
      settings: { visible: true, scale: 1, speed: 1, ...patch },
      state: 'idle',
    }))
  })

  it('loads and updates visibility scale and animation speed', async () => {
    const wrapper = mount(PetSettingsCard)
    await flushPromises()

    expect(wrapper.text()).toContain('墨团')
    await wrapper.get('[data-test="pet-visible"]').setValue(false)
    await wrapper.get('[data-test="pet-scale"]').setValue('1.25')
    await wrapper.get('[data-test="pet-speed"]').setValue('1.5')

    expect(apiMock.updatePetSettings).toHaveBeenNthCalledWith(1, { visible: false })
    expect(apiMock.updatePetSettings).toHaveBeenNthCalledWith(2, { scale: 1.25 })
    expect(apiMock.updatePetSettings).toHaveBeenNthCalledWith(3, { speed: 1.5 })
  })

  it('degrades safely in browser mode', async () => {
    apiMock.pet.mockResolvedValue({
      available: false, pet: null, settings: { visible: false, scale: 1, speed: 1 }, state: 'idle',
    })
    const wrapper = mount(PetSettingsCard)
    await flushPromises()

    expect(wrapper.text()).toContain('桌面应用')
    expect(wrapper.get('[data-test="pet-visible"]').attributes('disabled')).toBeDefined()
  })
})
