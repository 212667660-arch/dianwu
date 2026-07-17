import assert from 'node:assert/strict'
import { EventEmitter } from 'node:events'
import test from 'node:test'

import {
  createTrayController,
  mainWindowCloseAction,
  showMainWindow,
} from './tray-lifecycle.mjs'


class FakeTray extends EventEmitter {
  static instances = []

  constructor(icon) {
    super()
    this.icon = icon
    this.tooltip = ''
    this.menu = null
    this.destroyCalls = 0
    FakeTray.instances.push(this)
  }

  setToolTip(value) {
    this.tooltip = value
  }

  setContextMenu(value) {
    this.menu = value
  }

  destroy() {
    this.destroyCalls += 1
  }
}


const FakeMenu = {
  buildFromTemplate(template) {
    return { template }
  },
}


function visibleIcon() {
  return { isEmpty: () => false }
}


function fakeWindow({ minimized = false, destroyed = false } = {}) {
  const calls = []
  return {
    calls,
    isDestroyed: () => destroyed,
    isMinimized: () => minimized,
    restore: () => calls.push('restore'),
    show: () => calls.push('show'),
    focus: () => calls.push('focus'),
  }
}


function fixture({ window = fakeWindow(), requestQuit = () => {} } = {}) {
  FakeTray.instances.length = 0
  return createTrayController({
    Tray: FakeTray,
    Menu: FakeMenu,
    icon: visibleIcon(),
    getMainWindow: () => window,
    requestQuit,
  })
}


test('tray click restores, shows, and focuses the main window', () => {
  const window = fakeWindow({ minimized: true })
  const controller = fixture({ window })

  controller.tray.emit('click')

  assert.deepEqual(window.calls, ['restore', 'show', 'focus'])
  assert.equal(controller.tray.tooltip, '智学协作台')
  assert.equal(controller.tray.menu, controller.menu)
})


test('tray open and exit menu items call only their owned actions', () => {
  const window = fakeWindow()
  let quits = 0
  const controller = fixture({
    window,
    requestQuit: () => { quits += 1 },
  })

  const openItem = controller.menuTemplate.find(item => item.label === '打开智学协作台')
  const exitItem = controller.menuTemplate.find(item => item.label === '退出智学协作台')
  openItem.click()
  exitItem.click()

  assert.deepEqual(window.calls, ['show', 'focus'])
  assert.equal(quits, 1)
})


test('destroying the tray controller is idempotent', () => {
  const controller = fixture()

  controller.destroy()
  controller.destroy()

  assert.equal(controller.tray.destroyCalls, 1)
})


test('empty tray images fail before creating an invisible exit entrypoint', () => {
  FakeTray.instances.length = 0

  assert.throws(() => createTrayController({
    Tray: FakeTray,
    Menu: FakeMenu,
    icon: { isEmpty: () => true },
    getMainWindow: () => fakeWindow(),
    requestQuit: () => {},
  }), /tray icon/i)
  assert.equal(FakeTray.instances.length, 0)
})


test('showMainWindow ignores missing or destroyed windows', () => {
  assert.equal(showMainWindow(null), false)
  assert.equal(showMainWindow(fakeWindow({ destroyed: true })), false)
})


test('main window close hides only behind a usable tray', () => {
  assert.equal(mainWindowCloseAction({ isQuitting: false, hasTray: true }), 'hide')
  assert.equal(mainWindowCloseAction({ isQuitting: false, hasTray: false }), 'quit')
  assert.equal(mainWindowCloseAction({ isQuitting: true, hasTray: true }), 'allow')
})
