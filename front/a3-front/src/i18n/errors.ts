import { BackendApiError } from '@/api/transport'
import { i18n } from './index'

export function errorMessage(error: unknown): string {
  if (!(error instanceof BackendApiError)) return i18n.global.t('errors.unknown')
  const key = `errors.${error.code}`
  if (i18n.global.te(key)) return i18n.global.t(key)
  return i18n.global.t('errors.unknownWithReference', {
    code: error.code,
    requestId: error.requestId || i18n.global.t('common.notAvailable'),
  })
}
