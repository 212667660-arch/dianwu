export function mainWindowCloseAction({ isQuitting, hasTray }) {
  if (isQuitting) return 'allow'
  return hasTray ? 'hide' : 'quit'
}


export function showMainWindow(window) {
  if (!window || window.isDestroyed()) return false
  if (window.isMinimized()) window.restore()
  window.show()
  window.focus()
  return true
}


export function toggleMainWindow(window) {
  if (!window || window.isDestroyed()) return false
  if (window.isVisible() && !window.isMinimized() && window.isFocused()) {
    window.minimize()
    return true
  }
  return showMainWindow(window)
}


export function createTrayController({
  Tray,
  Menu,
  icon,
  getMainWindow,
  requestQuit,
  togglePet = () => {},
  getAiPaused = () => false,
  setAiPaused = async () => {},
}) {
  if (!icon || typeof icon.isEmpty !== 'function' || icon.isEmpty()) {
    throw new Error('Tray icon is empty.')
  }

  const tray = new Tray(icon)
  const show = () => showMainWindow(getMainWindow())
  const toggle = () => toggleMainWindow(getMainWindow())
  let menuTemplate = []
  let menu = null
  let destroyed = false

  const rebuild = () => {
    menuTemplate = [
      { label: '显示/最小化主窗口', click: toggle },
      { label: '显示/隐藏墨团', click: togglePet },
      {
        label: getAiPaused() ? '继续 AI' : '暂停 AI',
        click: async () => {
          await setAiPaused(!getAiPaused())
          rebuild()
        },
      },
      { type: 'separator' },
      { label: '完全退出', click: requestQuit },
    ]
    menu = Menu.buildFromTemplate(menuTemplate)
    tray.setContextMenu(menu)
  }

  tray.setToolTip('智学协作台')
  rebuild()
  tray.on('click', toggle)

  return {
    tray,
    get menu() { return menu },
    get menuTemplate() { return menuTemplate },
    show,
    toggle,
    rebuild,
    destroy() {
      if (destroyed) return
      destroyed = true
      tray.destroy()
    },
  }
}
