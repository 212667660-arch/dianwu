import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import test from 'node:test'
import { pathToFileURL } from 'node:url'

import { PET_ANIMATION_SPECS } from './pet-config.mjs'
import { createPetController } from './pet-controller.mjs'

function manifest(id = 'motuan') {
  return {
    id,
    displayName: id === 'motuan' ? '墨团' : '自定义伙伴',
    description: '测试角色。',
    spritesheetPath: 'spritesheet.webp',
    cell: { width: 192, height: 208 },
    grid: { columns: 8, rows: 9 },
    animations: Object.fromEntries(Object.entries(PET_ANIMATION_SPECS).map(([state, spec]) => [state, {
      row: spec.row,
      durations: [...spec.durations],
    }])),
  }
}

async function writePet(root, value = manifest()) {
  await fs.mkdir(root, { recursive: true })
  await fs.writeFile(path.join(root, 'pet.json'), JSON.stringify(value), 'utf8')
  await fs.writeFile(path.join(root, 'spritesheet.webp'), 'webp', 'utf8')
}

class FakeWebContents {
  constructor() { this.sent = []; this.destroyed = false }
  send(channel, payload) { this.sent.push({ channel, payload }) }
  isDestroyed() { return this.destroyed }
}

class FakeWindow {
  static created = []
  constructor(options) {
    this.options = options
    this.webContents = new FakeWebContents()
    this.visible = false
    this.destroyed = false
    this.bounds = { x: options.x, y: options.y, width: options.width, height: options.height }
    this.loaded = ''
    FakeWindow.created.push(this)
  }
  loadFile(file) { this.loaded = file }
  showInactive() { this.visible = true }
  hide() { this.visible = false }
  isVisible() { return this.visible }
  isDestroyed() { return this.destroyed }
  destroy() { this.destroyed = true }
  getBounds() { return { ...this.bounds } }
  setBounds(bounds) { this.bounds = { ...this.bounds, ...bounds } }
  setPosition(x, y) { this.bounds.x = x; this.bounds.y = y }
  on() {}
}

function fakeScreen() {
  const displays = [
    { id: 1, workArea: { x: 0, y: 0, width: 1200, height: 800 } },
    { id: 2, workArea: { x: 1200, y: -100, width: 1400, height: 1000 } },
  ]
  return {
    getAllDisplays: () => displays,
    getPrimaryDisplay: () => displays[0],
  }
}

async function fixture() {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'a3-pet-controller-'))
  const packagedPetDir = path.join(root, 'packaged-pet')
  const userDataDir = path.join(root, 'user-data')
  await writePet(packagedPetDir)
  FakeWindow.created = []
  const controller = createPetController({
    BrowserWindow: FakeWindow,
    screen: fakeScreen(),
    fs,
    userDataDir,
    packagedPetDir,
    petIndex: path.join(root, 'pet-index.html'),
    petPreload: path.join(root, 'pet-preload.cjs'),
    pathToFileURL,
  })
  return { root, userDataDir, packagedPetDir, controller }
}

test('controller loads a valid custom pet and falls back when custom manifest is invalid', async () => {
  const { userDataDir, packagedPetDir, controller, root } = await fixture()
  await writePet(path.join(userDataDir, 'pets', 'current'), manifest('custom-friend'))

  await controller.prepare()
  assert.equal(controller.snapshot().pet.id, 'custom-friend')

  await fs.writeFile(path.join(userDataDir, 'pets', 'current', 'pet.json'), '{"broken":true}', 'utf8')
  const second = createPetController({
    BrowserWindow: FakeWindow,
    screen: fakeScreen(),
    fs,
    userDataDir,
    packagedPetDir,
    petIndex: path.join(root, 'pet-index.html'),
    petPreload: path.join(root, 'pet-preload.cjs'),
    pathToFileURL,
  })
  await second.prepare()
  assert.equal(second.snapshot().pet.id, 'motuan')
})

test('controller creates a transparent frameless always-on-top pet window', async () => {
  const { controller, root } = await fixture()
  await controller.prepare()
  const window = controller.createWindow()

  assert.equal(window.options.transparent, true)
  assert.equal(window.options.frame, false)
  assert.equal(window.options.alwaysOnTop, true)
  assert.equal(window.options.skipTaskbar, true)
  assert.equal(window.options.resizable, false)
  assert.equal(window.options.webPreferences.preload, path.join(root, 'pet-preload.cjs'))
  assert.equal(window.options.webPreferences.sandbox, true)
  assert.equal(window.loaded, path.join(root, 'pet-index.html'))
  assert.equal(window.visible, true)
})

test('controller persists visibility scale speed and restores the saved position', async () => {
  const { userDataDir, packagedPetDir, controller, root } = await fixture()
  await controller.prepare()
  const window = controller.createWindow()

  await controller.updateSettings({ visible: false, scale: 1.5, speed: 0.75 })
  assert.equal(window.visible, false)
  assert.equal(window.getBounds().width, 288)
  assert.equal(window.getBounds().height, 312)
  assert.equal(controller.snapshot().settings.speed, 0.75)
  assert.equal(controller.snapshot().settings.soundEnabled, true)
  assert.equal(controller.snapshot().settings.soundVolume, 0.5)
  assert.equal(controller.snapshot().settings.voiceEnabled, false)
  assert.equal(controller.snapshot().settings.voiceVolume, 0.75)

  controller.beginDrag({ screenX: 900, screenY: 500 })
  await controller.moveDrag({ screenX: 2500, screenY: 950 })
  await controller.endDrag()
  assert.equal(window.getBounds().x, 2312)
  assert.equal(window.getBounds().y, 588)

  const restored = createPetController({
    BrowserWindow: FakeWindow,
    screen: fakeScreen(),
    fs,
    userDataDir,
    packagedPetDir,
    petIndex: path.join(root, 'pet-index.html'),
    petPreload: path.join(root, 'pet-preload.cjs'),
    pathToFileURL,
  })
  await restored.prepare()
  const restoredWindow = restored.createWindow({ forceHidden: true })
  assert.equal(restored.snapshot().settings.scale, 1.5)
  assert.equal(restoredWindow.getBounds().x, 2312)
  assert.equal(restoredWindow.getBounds().y, 588)
  assert.equal(restoredWindow.visible, false)
})

test('controller keeps authoritative bounds when Electron reports a transient resize', async () => {
  const { controller, userDataDir } = await fixture()
  await controller.prepare()
  const window = controller.createWindow()
  await controller.updateSettings({ scale: 1.5 })

  window.bounds = { x: 0, y: 0, width: 1200, height: 800 }
  controller.beginDrag({ screenX: 500, screenY: 400 })
  await controller.moveDrag({ screenX: 540, screenY: 420 })
  await controller.endDrag()

  const stored = JSON.parse(await fs.readFile(path.join(userDataDir, 'pet-settings.json'), 'utf8'))
  assert.deepEqual(stored.position, { x: 912, y: 488, width: 288, height: 312 })
})

test('repeated click-like drag cycles preserve pet dimensions and scale', async () => {
  const { controller } = await fixture()
  await controller.prepare()
  const window = controller.createWindow()
  const before = window.getBounds()

  for (let index = 0; index < 100; index += 1) {
    controller.beginDrag({ screenX: 500, screenY: 300 })
    await controller.moveDrag({ screenX: 500, screenY: 300 })
    await controller.endDrag()
  }

  assert.deepEqual(window.getBounds(), before)
  assert.equal(controller.snapshot().settings.scale, 1)
})

test('controller broadcasts task and drag states then restores the task state', async () => {
  const { controller } = await fixture()
  await controller.prepare()
  const window = controller.createWindow()

  controller.setTaskState('review')
  controller.beginDrag({ screenX: 1000, screenY: 500 })
  await controller.moveDrag({ screenX: 940, screenY: 500 })
  await controller.endDrag()

  assert.deepEqual(window.webContents.sent.filter(value => value.channel === 'a3:pet-state').map(value => value.payload.state), [
    'review', 'running-left', 'review',
  ])
  assert.throws(() => controller.setTaskState('jumping'))
})

test('controller exposes separate sender checks for main and pet windows', async () => {
  const { controller } = await fixture()
  await controller.prepare()
  const petWindow = controller.createWindow()
  const mainContents = new FakeWebContents()
  controller.setMainWebContents(mainContents)

  assert.equal(controller.isMainSender({ sender: mainContents }), true)
  assert.equal(controller.isMainSender({ sender: petWindow.webContents }), false)
  assert.equal(controller.isPetSender({ sender: petWindow.webContents }), true)
  assert.equal(controller.isPetSender({ sender: mainContents }), false)
})

test('controller reloads a changed character without losing the main sender', async () => {
  const { controller, userDataDir } = await fixture()
  await controller.prepare()
  const first = controller.createWindow()
  const mainContents = new FakeWebContents()
  controller.setMainWebContents(mainContents)
  await writePet(path.join(userDataDir, 'pets', 'current'), manifest('custom-friend'))

  const second = await controller.reloadPet()
  assert.equal(first.destroyed, true)
  assert.notEqual(second, first)
  assert.equal(controller.snapshot().pet.id, 'custom-friend')
  assert.equal(controller.isMainSender({ sender: mainContents }), true)
})
