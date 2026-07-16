import assert from 'node:assert/strict'
import test from 'node:test'

import {
  PET_ANIMATION_SPECS,
  PET_SCALE_VALUES,
  PET_SPEED_VALUES,
  PET_TASK_STATES,
  clampPetBounds,
  defaultPetBounds,
  validatePetManifest,
  validatePetSettingsPatch,
} from './pet-config.mjs'

function manifest() {
  return {
    id: 'motuan',
    displayName: '墨团',
    description: '住在书页边缘的青墨学习精灵。',
    spritesheetPath: 'spritesheet.webp',
    cell: { width: 192, height: 208 },
    grid: { columns: 8, rows: 9 },
    animations: Object.fromEntries(
      Object.entries(PET_ANIMATION_SPECS).map(([state, spec]) => [state, {
        row: spec.row,
        durations: [...spec.durations],
      }]),
    ),
  }
}

test('pet manifest requires the fixed nine animation rows and safe relative spritesheet', () => {
  const value = validatePetManifest(manifest())

  assert.equal(value.cell.width, 192)
  assert.equal(value.grid.rows, 9)
  assert.deepEqual(Object.keys(value.animations), [
    'idle', 'running-right', 'running-left', 'waving', 'jumping',
    'failed', 'waiting', 'running', 'review',
  ])
  assert.equal(value.animations.review.row, 8)

  assert.throws(() => validatePetManifest({ ...manifest(), spritesheetPath: '../secret.webp' }))
  assert.throws(() => validatePetManifest({ ...manifest(), extra: true }))
  const missing = manifest()
  delete missing.animations.review
  assert.throws(() => validatePetManifest(missing))
  const wrongRow = manifest()
  wrongRow.animations.waiting.row = 7
  assert.throws(() => validatePetManifest(wrongRow))
})

test('pet settings accept only fixed visibility scale and speed values', () => {
  assert.deepEqual(PET_SCALE_VALUES, [0.5, 0.75, 1, 1.25, 1.5])
  assert.deepEqual(PET_SPEED_VALUES, [0.5, 0.75, 1, 1.25, 1.5, 2])
  assert.deepEqual(PET_TASK_STATES, ['idle', 'running', 'waiting', 'review', 'failed'])
  assert.deepEqual(validatePetSettingsPatch({ visible: false, scale: 1.25, speed: 1.5 }), {
    visible: false,
    scale: 1.25,
    speed: 1.5,
  })
  assert.deepEqual(validatePetSettingsPatch({ visible: true }), { visible: true })
  assert.throws(() => validatePetSettingsPatch({ scale: 1.1 }))
  assert.throws(() => validatePetSettingsPatch({ speed: Infinity }))
  assert.throws(() => validatePetSettingsPatch({ visible: true, path: 'C:\\secret' }))
})

test('pet bounds clamp inside the nearest display including negative desktop coordinates', () => {
  const displays = [
    { id: 1, workArea: { x: -1600, y: 0, width: 1600, height: 900 } },
    { id: 2, workArea: { x: 0, y: -120, width: 1920, height: 1080 } },
  ]

  assert.deepEqual(clampPetBounds({ x: -1700, y: 850, width: 192, height: 208 }, displays), {
    x: -1600,
    y: 692,
    width: 192,
    height: 208,
    displayId: 1,
  })
  assert.deepEqual(clampPetBounds({ x: 1900, y: -300, width: 288, height: 312 }, displays), {
    x: 1632,
    y: -120,
    width: 288,
    height: 312,
    displayId: 2,
  })
})

test('default pet bounds use a safe bottom-right margin in DIP coordinates', () => {
  assert.deepEqual(defaultPetBounds(
    { id: 3, workArea: { x: 100, y: 50, width: 1200, height: 800 } },
    192,
    208,
  ), {
    x: 1084,
    y: 618,
    width: 192,
    height: 208,
    displayId: 3,
  })
})
