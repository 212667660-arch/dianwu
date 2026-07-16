import path from 'node:path'

export const PET_ANIMATION_SPECS = Object.freeze({
  idle: Object.freeze({ row: 0, durations: Object.freeze([280, 110, 110, 140, 140, 320]) }),
  'running-right': Object.freeze({ row: 1, durations: Object.freeze([120, 120, 120, 120, 120, 120, 120, 220]) }),
  'running-left': Object.freeze({ row: 2, durations: Object.freeze([120, 120, 120, 120, 120, 120, 120, 220]) }),
  waving: Object.freeze({ row: 3, durations: Object.freeze([140, 140, 140, 280]) }),
  jumping: Object.freeze({ row: 4, durations: Object.freeze([140, 140, 140, 140, 280]) }),
  failed: Object.freeze({ row: 5, durations: Object.freeze([140, 140, 140, 140, 140, 140, 140, 240]) }),
  waiting: Object.freeze({ row: 6, durations: Object.freeze([150, 150, 150, 150, 150, 260]) }),
  running: Object.freeze({ row: 7, durations: Object.freeze([120, 120, 120, 120, 120, 220]) }),
  review: Object.freeze({ row: 8, durations: Object.freeze([150, 150, 150, 150, 150, 280]) }),
})

export const PET_SCALE_VALUES = Object.freeze([0.5, 0.75, 1, 1.25, 1.5])
export const PET_SPEED_VALUES = Object.freeze([0.5, 0.75, 1, 1.25, 1.5, 2])
export const PET_VOLUME_VALUES = Object.freeze([0, 0.25, 0.5, 0.75, 1])
export const PET_TASK_STATES = Object.freeze(['idle', 'running', 'waiting', 'review', 'failed'])

const MANIFEST_FIELDS = new Set([
  'id', 'displayName', 'description', 'spritesheetPath', 'cell', 'grid', 'animations',
])
const SETTINGS_FIELDS = new Set(['visible', 'scale', 'speed', 'soundEnabled', 'soundVolume', 'voiceEnabled', 'voiceVolume'])

export function validatePetManifest(input) {
  if (!isPlainObject(input) || !hasOnlyFields(input, MANIFEST_FIELDS)) {
    throw new TypeError('Pet manifest fields are invalid.')
  }
  const id = normalizedString(input.id, 1, 64)
  if (!/^[a-z0-9][a-z0-9_-]*$/.test(id)) throw new TypeError('Pet id is invalid.')
  const displayName = normalizedString(input.displayName, 1, 64)
  const description = normalizedString(input.description, 1, 240)
  const spritesheetPath = normalizedString(input.spritesheetPath, 1, 128)
  if (
    path.isAbsolute(spritesheetPath)
    || path.basename(spritesheetPath) !== spritesheetPath
    || path.extname(spritesheetPath).toLowerCase() !== '.webp'
  ) {
    throw new TypeError('Pet spritesheet path is invalid.')
  }
  if (!exactNumberObject(input.cell, { width: 192, height: 208 })) {
    throw new TypeError('Pet cell geometry is invalid.')
  }
  if (!exactNumberObject(input.grid, { columns: 8, rows: 9 })) {
    throw new TypeError('Pet grid geometry is invalid.')
  }
  if (!isPlainObject(input.animations) || !hasOnlyFields(input.animations, new Set(Object.keys(PET_ANIMATION_SPECS)))) {
    throw new TypeError('Pet animation states are invalid.')
  }
  const animations = {}
  for (const [state, expected] of Object.entries(PET_ANIMATION_SPECS)) {
    const animation = input.animations[state]
    if (!isPlainObject(animation) || !hasOnlyFields(animation, new Set(['row', 'durations']))) {
      throw new TypeError(`Pet animation ${state} is invalid.`)
    }
    if (animation.row !== expected.row || !Array.isArray(animation.durations) || animation.durations.length !== expected.durations.length) {
      throw new TypeError(`Pet animation ${state} geometry is invalid.`)
    }
    const durations = animation.durations.map(value => {
      if (!Number.isInteger(value) || value < 40 || value > 5000) {
        throw new TypeError(`Pet animation ${state} duration is invalid.`)
      }
      return value
    })
    animations[state] = { row: expected.row, durations }
  }
  return {
    id,
    displayName,
    description,
    spritesheetPath,
    cell: { width: 192, height: 208 },
    grid: { columns: 8, rows: 9 },
    animations,
  }
}

export function parsePetManifestText(input) {
  if (typeof input !== 'string') throw new TypeError('Pet manifest text is invalid.')
  return validatePetManifest(JSON.parse(input.replace(/^\uFEFF/, '')))
}

export function validatePetSettingsPatch(input) {
  if (!isPlainObject(input) || !hasNoUnknownFields(input, SETTINGS_FIELDS) || Object.keys(input).length === 0) {
    throw new TypeError('Pet settings fields are invalid.')
  }
  const value = {}
  if (Object.hasOwn(input, 'visible')) {
    if (typeof input.visible !== 'boolean') throw new TypeError('Pet visibility is invalid.')
    value.visible = input.visible
  }
  if (Object.hasOwn(input, 'scale')) {
    if (!PET_SCALE_VALUES.includes(input.scale)) throw new TypeError('Pet scale is invalid.')
    value.scale = input.scale
  }
  if (Object.hasOwn(input, 'speed')) {
    if (!PET_SPEED_VALUES.includes(input.speed)) throw new TypeError('Pet speed is invalid.')
    value.speed = input.speed
  }
  for (const field of ['soundEnabled', 'voiceEnabled']) {
    if (Object.hasOwn(input, field)) {
      if (typeof input[field] !== 'boolean') throw new TypeError(`Pet ${field} is invalid.`)
      value[field] = input[field]
    }
  }
  for (const field of ['soundVolume', 'voiceVolume']) {
    if (Object.hasOwn(input, field)) {
      if (!PET_VOLUME_VALUES.includes(input[field])) throw new TypeError(`Pet ${field} is invalid.`)
      value[field] = input[field]
    }
  }
  return value
}

export function clampPetBounds(bounds, displays) {
  if (!isBounds(bounds) || !Array.isArray(displays) || displays.length === 0) {
    throw new TypeError('Pet bounds or displays are invalid.')
  }
  const center = { x: bounds.x + bounds.width / 2, y: bounds.y + bounds.height / 2 }
  const display = [...displays].sort((left, right) => distanceToWorkArea(center, left.workArea) - distanceToWorkArea(center, right.workArea))[0]
  if (!display || !isBounds(display.workArea)) throw new TypeError('Display work area is invalid.')
  const area = display.workArea
  const width = Math.min(bounds.width, area.width)
  const height = Math.min(bounds.height, area.height)
  return {
    x: Math.round(clamp(bounds.x, area.x, area.x + area.width - width)),
    y: Math.round(clamp(bounds.y, area.y, area.y + area.height - height)),
    width: Math.round(width),
    height: Math.round(height),
    displayId: display.id,
  }
}

export function defaultPetBounds(display, width, height, margin = 24) {
  if (!display || !isBounds(display.workArea) || !Number.isFinite(width) || !Number.isFinite(height)) {
    throw new TypeError('Default pet display geometry is invalid.')
  }
  const area = display.workArea
  return {
    x: Math.round(area.x + area.width - width - margin),
    y: Math.round(area.y + area.height - height - margin),
    width: Math.round(width),
    height: Math.round(height),
    displayId: display.id,
  }
}

function distanceToWorkArea(point, area) {
  if (!isBounds(area)) return Number.POSITIVE_INFINITY
  const nearestX = clamp(point.x, area.x, area.x + area.width)
  const nearestY = clamp(point.y, area.y, area.y + area.height)
  return (point.x - nearestX) ** 2 + (point.y - nearestY) ** 2
}

function exactNumberObject(value, expected) {
  return isPlainObject(value)
    && hasOnlyFields(value, new Set(Object.keys(expected)))
    && Object.entries(expected).every(([key, number]) => value[key] === number)
}

function normalizedString(value, minLength, maxLength) {
  if (typeof value !== 'string') throw new TypeError('Pet text is invalid.')
  const normalized = value.trim()
  if (normalized.length < minLength || normalized.length > maxLength || /[\0\r\n]/.test(normalized)) {
    throw new TypeError('Pet text is invalid.')
  }
  return normalized
}

function hasOnlyFields(value, allowed) {
  return hasNoUnknownFields(value, allowed) && [...allowed].every(key => Object.hasOwn(value, key))
}

function hasNoUnknownFields(value, allowed) {
  return Object.keys(value).every(key => allowed.has(key))
}

function isPlainObject(value) {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value) && Object.getPrototypeOf(value) === Object.prototype
}

function isBounds(value) {
  return isPlainObject(value)
    && ['x', 'y', 'width', 'height'].every(key => Number.isFinite(value[key]))
    && value.width > 0
    && value.height > 0
}

function clamp(value, minimum, maximum) {
  return Math.min(Math.max(value, minimum), maximum)
}
