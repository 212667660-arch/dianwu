/// <reference types="vite/client" />

import type { DesktopBridge } from './api/transport'

declare global {
  interface Window {
    a3Desktop?: DesktopBridge
  }
}

export {}
