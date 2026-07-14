export type RouterHistoryMode = 'hash' | 'web'

export function routerHistoryMode(protocol: string | undefined): RouterHistoryMode {
  return protocol === 'file:' ? 'hash' : 'web'
}
