import { afterEach } from 'vitest'
import { config } from '@vue/test-utils'
import { activateLocale, i18n } from '@/i18n'

config.global.plugins = [i18n]

afterEach(() => {
  localStorage.clear()
  activateLocale('zh-CN')
})
