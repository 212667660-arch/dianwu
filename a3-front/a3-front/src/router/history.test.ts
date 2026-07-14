import { describe, expect, it } from 'vitest'
import { routerHistoryMode } from './history'

describe('routerHistoryMode', () => {
  it('uses hash history for the Electron file protocol', () => {
    expect(routerHistoryMode('file:')).toBe('hash')
  })

  it.each(['http:', 'https:', undefined])('uses web history outside Electron files (%s)', (protocol) => {
    expect(routerHistoryMode(protocol)).toBe('web')
  })
})
