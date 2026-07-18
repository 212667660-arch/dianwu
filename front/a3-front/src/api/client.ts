import { DesktopApiError } from './transport'
import { errorMessage as webErrorMessage } from './web-transport'

export function errorMessage(error: unknown): string {
  if (error instanceof DesktopApiError) return error.message
  return webErrorMessage(error)
}
