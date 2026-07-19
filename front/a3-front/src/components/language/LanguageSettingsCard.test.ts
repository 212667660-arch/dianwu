import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import { activateLocale, installLocaleMessages } from '@/i18n'
import { BUILT_IN_MESSAGES } from '@/i18n/catalog'
import LanguageSettingsCard from './LanguageSettingsCard.vue'

const languages = [
  { locale: 'en-US', nativeName: 'English (United States)', version: '1.0.0', status: 'available' as const },
  { locale: 'zh-TW', nativeName: '繁體中文（台灣）', version: '1.0.0', status: 'installed' as const },
]

function mountCard(desktopAvailable: boolean) {
  return mount(LanguageSettingsCard, {
    props: {
      activeLocale: 'zh-CN',
      languages,
      busyLocale: null,
      progress: null,
      desktopAvailable,
    },
  })
}

describe('LanguageSettingsCard', () => {
  it('always shows built-in Simplified Chinese and the exact UI/content locale notice', () => {
    const wrapper = mountCard(false)

    expect(wrapper.text()).toContain('简体中文')
    expect(wrapper.text()).toContain(BUILT_IN_MESSAGES.views.desktopSettings.language.contentFollowsUi)
  })

  it('shows download and import controls only with desktop language capability', () => {
    const browser = mountCard(false)
    expect(browser.find('[data-testid="language-download-en-US"]').exists()).toBe(false)
    expect(browser.find('[data-testid="language-import"]').exists()).toBe(false)

    const desktop = mountCard(true)
    expect(desktop.get('[data-testid="language-download-en-US"]').isVisible()).toBe(true)
    expect(desktop.get('[data-testid="language-import"]').isVisible()).toBe(true)
  })

  it('emits only fixed language actions and locale arguments', async () => {
    const wrapper = mountCard(true)

    await wrapper.get('[data-testid="language-refresh"]').trigger('click')
    await wrapper.get('[data-testid="language-download-en-US"]').trigger('click')
    await wrapper.get('[data-testid="language-activate-zh-TW"]').trigger('click')
    await wrapper.get('[data-testid="language-remove-zh-TW"]').trigger('click')
    await wrapper.get('[data-testid="language-import"]').trigger('click')

    expect(wrapper.emitted('refresh')).toEqual([[]])
    expect(wrapper.emitted('download')).toEqual([['en-US']])
    expect(wrapper.emitted('activate')).toEqual([['zh-TW']])
    expect(wrapper.emitted('remove')).toEqual([['zh-TW']])
    expect(wrapper.emitted('import')).toEqual([[]])
  })

  it('switches shell messages at runtime without translating language native names', () => {
    installLocaleMessages('en-US', {
      views: { desktopSettings: { language: {
        title: 'Language',
        contentFollowsUi: 'The interface and newly generated AI content use this language. Existing history and user files are unchanged.',
        builtIn: 'Built in',
        refresh: 'Refresh',
        import: 'Import language pack',
        download: 'Download',
        activate: 'Use language',
        remove: 'Remove',
        active: 'Active',
        installed: 'Installed',
        available: 'Available',
        builtInName: 'Simplified Chinese',
      } } },
    })
    activateLocale('en-US')

    const wrapper = mountCard(true)
    expect(wrapper.text()).toContain('Language')
    expect(wrapper.text()).toContain('The interface and newly generated AI content use this language.')
    expect(wrapper.text()).toContain('繁體中文（台灣）')
  })
})
