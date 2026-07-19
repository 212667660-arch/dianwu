import { afterEach } from 'vitest'
import { config } from '@vue/test-utils'
import { i18n, resetLocaleRuntimeForTests } from '@/i18n'

config.global.plugins = [i18n]

afterEach(() => {
  localStorage.clear()
  resetLocaleRuntimeForTests()
})
