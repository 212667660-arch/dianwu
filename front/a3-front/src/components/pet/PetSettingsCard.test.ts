import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { activateLocale, installLocaleMessages } from '@/i18n'

const apiMock = vi.hoisted(() => ({
  pet: vi.fn(),
  updatePetSettings: vi.fn(),
  choosePetCharacter: vi.fn(),
  resetPetCharacter: vi.fn(),
  setPetTaskState: vi.fn(),
}))
vi.mock('@/api', () => ({ backendApi: apiMock }))

import PetSettingsCard from './PetSettingsCard.vue'

describe('PetSettingsCard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiMock.pet.mockResolvedValue({
      available: true,
      pet: { id: 'motuan', displayName: '墨团', description: '学习伙伴' },
      settings: { visible: true, alwaysOnTop: true, scale: 1, speed: 1, soundEnabled: true, soundVolume: 0.5, voiceEnabled: false, voiceVolume: 0.75 },
      state: 'idle',
    })
    apiMock.updatePetSettings.mockImplementation(async patch => ({
      available: true,
      pet: { id: 'motuan', displayName: '墨团', description: '学习伙伴' },
      settings: { visible: true, alwaysOnTop: true, scale: 1, speed: 1, soundEnabled: true, soundVolume: 0.5, voiceEnabled: false, voiceVolume: 0.75, ...patch },
      state: 'idle',
    }))
  })
  apiMock.setPetTaskState.mockImplementation(async state => state)

  it('loads and updates visibility scale and animation speed', async () => {
    const wrapper = mount(PetSettingsCard)
    await flushPromises()

    expect(wrapper.text()).toContain('墨团')
    await wrapper.get('[data-test="pet-visible"]').setValue(false)
    await wrapper.get('[data-test="pet-scale"]').setValue('1.25')
    await wrapper.get('[data-test="pet-speed"]').setValue('1.5')
    await wrapper.get('[data-test="pet-sound-volume"]').setValue('0.25')
    await wrapper.get('[data-test="pet-sound-enabled"]').setValue(false)
    await wrapper.get('[data-test="pet-voice-enabled"]').setValue(true)
    await wrapper.get('[data-test="pet-voice-volume"]').setValue('1')

    expect(apiMock.updatePetSettings).toHaveBeenNthCalledWith(1, { visible: false })
    expect(apiMock.updatePetSettings).toHaveBeenNthCalledWith(2, { scale: 1.25 })
    expect(apiMock.updatePetSettings).toHaveBeenNthCalledWith(3, { speed: 1.5 })
    expect(apiMock.updatePetSettings).toHaveBeenNthCalledWith(4, { soundVolume: 0.25 })
    expect(apiMock.updatePetSettings).toHaveBeenNthCalledWith(5, { soundEnabled: false })
    expect(apiMock.updatePetSettings).toHaveBeenNthCalledWith(6, { voiceEnabled: true })
    expect(apiMock.updatePetSettings).toHaveBeenNthCalledWith(7, { voiceVolume: 1 })
  })

  it('toggles always-on-top and previews learning-state actions', async () => {
    const wrapper = mount(PetSettingsCard)
    await flushPromises()

    await wrapper.get('[data-test="pet-always-on-top"]').setValue(false)
    await wrapper.get('[data-test="pet-preview-running"]').trigger('click')
    await flushPromises()

    expect(apiMock.updatePetSettings).toHaveBeenCalledWith({ alwaysOnTop: false })
    expect(apiMock.setPetTaskState).toHaveBeenCalledWith('running')
    expect(wrapper.text()).toContain('正在努力')
  })

  it('degrades safely in browser mode', async () => {
    apiMock.pet.mockResolvedValue({
      available: false, pet: null, settings: { visible: false, scale: 1, speed: 1, soundEnabled: false, soundVolume: 0.5, voiceEnabled: false, voiceVolume: 0.75 }, state: 'idle',
    })
    const wrapper = mount(PetSettingsCard)
    await flushPromises()

    expect(wrapper.text()).toContain('桌面应用')
    expect(wrapper.get('[data-test="pet-visible"]').attributes('disabled')).toBeDefined()
  })

  it('imports and resets the current character through fixed desktop actions', async () => {
    apiMock.choosePetCharacter = vi.fn().mockResolvedValue({
      available: true, pet: { id: 'friend', displayName: '新伙伴', description: '角色' },
      settings: { visible: true, scale: 1, speed: 1, soundEnabled: true, soundVolume: 0.5, voiceEnabled: false, voiceVolume: 0.75 }, state: 'idle',
    })
    apiMock.resetPetCharacter = vi.fn().mockResolvedValue({
      available: true, pet: { id: 'motuan', displayName: '墨团', description: '角色' },
      settings: { visible: true, scale: 1, speed: 1, soundEnabled: true, soundVolume: 0.5, voiceEnabled: false, voiceVolume: 0.75 }, state: 'idle',
    })
    const wrapper = mount(PetSettingsCard)
    await flushPromises()
    await wrapper.get('[data-test="pet-import"]').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('新伙伴')
    await wrapper.get('[data-test="pet-reset"]').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('墨团')
  })

  it('keeps reset available when a custom package reuses the built-in id', async () => {
    apiMock.pet.mockResolvedValue({
      available: true, pet: { id: 'motuan', displayName: '同名自定义伙伴', description: '角色' },
      settings: { visible: true, scale: 1, speed: 1, soundEnabled: true, soundVolume: 0.5, voiceEnabled: false, voiceVolume: 0.75 }, state: 'idle',
    })
    apiMock.resetPetCharacter.mockResolvedValue({
      available: true, pet: { id: 'motuan', displayName: '墨团', description: '角色' },
      settings: { visible: true, scale: 1, speed: 1, soundEnabled: true, soundVolume: 0.5, voiceEnabled: false, voiceVolume: 0.75 }, state: 'idle',
    })
    const wrapper = mount(PetSettingsCard)
    await flushPromises()

    expect(wrapper.get('[data-test="pet-reset"]').attributes('disabled')).toBeUndefined()
    await wrapper.get('[data-test="pet-reset"]').trigger('click')
    await flushPromises()
    expect(apiMock.resetPetCharacter).toHaveBeenCalledOnce()
  })

  it('renders injected English pet labels without changing character metadata', async () => {
    installLocaleMessages('en-US', { components: { petSettings: { learningPartnerDesktop: 'Desktop learning companion', showCompanion: 'Show companion' } } })
    activateLocale('en-US')
    const wrapper = mount(PetSettingsCard)
    await flushPromises()

    expect(wrapper.text()).toContain('Desktop learning companion')
    expect(wrapper.text()).toContain('Show companion')
    expect(wrapper.text()).toContain('墨团')
  })
})
