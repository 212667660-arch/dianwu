import { bytesToHex } from '@noble/hashes/utils'
import { sha256 } from '@noble/hashes/sha256'
import { describe, expect, it } from 'vitest'

import {
  BASE_CATALOG_HASH,
  BUILT_IN_MESSAGES,
  CATALOG_VERSION,
  flattenMessages,
  placeholdersFor,
} from './catalog'

const FORBIDDEN_KEYS = new Set(['__proto__', 'prototype', 'constructor'])

describe('built-in zh-CN catalog contract', () => {
  it('publishes the versioned required catalog keys', () => {
    expect(CATALOG_VERSION).toBe(1)
    const flat = flattenMessages(BUILT_IN_MESSAGES)
    expect(flat['navigation.dashboard']).toBeTruthy()
    expect(flat['views.desktopSettings.language.title']).toBeTruthy()
    expect(flat['errors.BACKEND_UNAVAILABLE']).toBeTruthy()
    expect(flat['desktop.tray.quit']).toBeTruthy()
  })

  it('extracts stable sorted placeholder names', () => {
    expect(placeholdersFor('已导出 {fileName}')).toEqual(['fileName'])
    expect(placeholdersFor('{zeta}、{alpha}、{zeta}')).toEqual(['alpha', 'zeta'])
  })

  it('contains only safe, non-empty string leaves', () => {
    const visit = (value: unknown, path: string[] = []): void => {
      expect(Array.isArray(value), path.join('.')).toBe(false)
      expect(value, path.join('.')).not.toBeNull()
      if (typeof value === 'object') {
        for (const [key, child] of Object.entries(value as Record<string, unknown>)) {
          expect(FORBIDDEN_KEYS.has(key), [...path, key].join('.')).toBe(false)
          visit(child, [...path, key])
        }
        return
      }
      expect(typeof value, path.join('.')).toBe('string')
      expect((value as string).trim(), path.join('.')).not.toBe('')
      expect(value as string, path.join('.')).not.toMatch(/<\/?[A-Za-z][^>]*>/)
      expect(value as string, path.join('.')).not.toMatch(/[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F]/)
    }
    visit(BUILT_IN_MESSAGES)
  })

  it('rejects invalid catalog structures while flattening', () => {
    expect(() => flattenMessages({ list: ['invalid'] })).toThrow(/array/i)
    expect(() => flattenMessages({ missing: null })).toThrow(/null/i)
    expect(() => flattenMessages(JSON.parse('{"constructor":"invalid"}'))).toThrow(/forbidden/i)
    expect(() => flattenMessages({ count: 1 })).toThrow(/string/i)
  })

  it('derives a deterministic uppercase SHA-256 catalog digest', () => {
    const entries = Object.entries(flattenMessages(BUILT_IN_MESSAGES))
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([key, message]) => [key, placeholdersFor(message)] as const)
    const payload = JSON.stringify({ catalog_version: CATALOG_VERSION, messages: entries })
    const independentHash = bytesToHex(sha256(new TextEncoder().encode(payload))).toUpperCase()

    expect(BASE_CATALOG_HASH).toMatch(/^[A-F0-9]{64}$/)
    expect(BASE_CATALOG_HASH).toBe(independentHash)
    expect(BASE_CATALOG_HASH).toBe('BF48789B3A7427B8DF7E7E21913056E8D3E60B7EA386946F9296A63B02B7626F')
  })
})
