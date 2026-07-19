import { sha256 } from '@noble/hashes/sha256'
import { bytesToHex } from '@noble/hashes/utils'
import canonicalize from 'canonicalize'

import common from './locales/zh-CN/messages/common.json'
import navigation from './locales/zh-CN/messages/navigation.json'
import dashboard from './locales/zh-CN/messages/views/dashboard.json'
import profile from './locales/zh-CN/messages/views/profile.json'
import agents from './locales/zh-CN/messages/views/agents.json'
import learningPath from './locales/zh-CN/messages/views/learning-path.json'
import tutor from './locales/zh-CN/messages/views/tutor.json'
import assessment from './locales/zh-CN/messages/views/assessment.json'
import knowledge from './locales/zh-CN/messages/views/knowledge.json'
import modelSettings from './locales/zh-CN/messages/views/model-settings.json'
import desktopSettings from './locales/zh-CN/messages/views/desktop-settings.json'
import onboarding from './locales/zh-CN/messages/views/onboarding.json'
import components from './locales/zh-CN/messages/components.json'
import statuses from './locales/zh-CN/messages/statuses.json'
import errors from './locales/zh-CN/messages/errors.json'
import desktop from './locales/zh-CN/messages/desktop.json'
import pet from './locales/zh-CN/messages/pet.json'
import sourceInventory from './locales/zh-CN/messages/source-inventory.json'

export const CATALOG_VERSION = 1 as const
export const BUILT_IN_LOCALE = 'zh-CN' as const
export const DOWNLOADABLE_LOCALES = ['en-US', 'zh-TW'] as const

function deepFreeze<T>(value: T): T {
  if (value && typeof value === 'object') {
    for (const child of Object.values(value as Record<string, unknown>)) deepFreeze(child)
    Object.freeze(value)
  }
  return value
}

export const BUILT_IN_MESSAGES = deepFreeze({
  common,
  navigation,
  views: {
    dashboard,
    profile,
    agents,
    learningPath,
    tutor,
    assessment,
    knowledge,
    modelSettings,
    desktopSettings,
    onboarding,
  },
  components,
  statuses,
  errors,
  desktop,
  pet,
  sourceInventory,
} as const)

const FORBIDDEN_KEYS = new Set(['__proto__', 'prototype', 'constructor'])

export function flattenMessages(messages: unknown): Record<string, string> {
  const flattened: Record<string, string> = Object.create(null)

  const visit = (value: unknown, path: string[]): void => {
    if (value === null) throw new TypeError(`Catalog value at ${path.join('.') || '<root>'} must not be null`)
    if (Array.isArray(value)) throw new TypeError(`Catalog value at ${path.join('.') || '<root>'} must not be an array`)
    if (typeof value === 'string') {
      if (path.length === 0) throw new TypeError('Catalog root must be an object')
      flattened[path.join('.')] = value
      return
    }
    if (typeof value !== 'object') {
      throw new TypeError(`Catalog leaf at ${path.join('.') || '<root>'} must be a string`)
    }
    for (const [key, child] of Object.entries(value as Record<string, unknown>)) {
      if (FORBIDDEN_KEYS.has(key)) throw new TypeError(`Catalog contains forbidden key: ${key}`)
      visit(child, [...path, key])
    }
  }

  visit(messages, [])
  return flattened
}

export function placeholdersFor(message: string): string[] {
  const placeholders = new Set<string>()
  for (const match of message.matchAll(/\{([A-Za-z][A-Za-z0-9_]*)\}/g)) placeholders.add(match[1])
  return [...placeholders].sort(compareUnicodeCodePoints)
}

function compareUnicodeCodePoints(left: string, right: string): number {
  const leftPoints = [...left]
  const rightPoints = [...right]
  for (let index = 0; index < Math.min(leftPoints.length, rightPoints.length); index += 1) {
    const difference = leftPoints[index].codePointAt(0)! - rightPoints[index].codePointAt(0)!
    if (difference !== 0) return difference
  }
  return leftPoints.length - rightPoints.length
}

export function buildBaseCatalogPayload(): string {
  const messages = Object.entries(flattenMessages(BUILT_IN_MESSAGES))
    .sort(([left], [right]) => compareUnicodeCodePoints(left, right))
    .map(([key, message]) => [key, placeholdersFor(message)] as const)
  const payload = canonicalize({ catalog_version: CATALOG_VERSION, messages })
  if (payload === undefined) throw new TypeError('Unable to canonicalize the built-in catalog payload')
  return payload
}

export const BASE_CATALOG_HASH = bytesToHex(
  sha256(new TextEncoder().encode(buildBaseCatalogPayload())),
).toUpperCase()
