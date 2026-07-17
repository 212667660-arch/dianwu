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


export function createTrayController({
  Tray,
  Menu,
  icon,
  getMainWindow,
  requestQuit,
  showPet = () => {},
  getAiPaused = () => false,
  setAiPaused = async () => {},
}) {
  if (!icon || typeof icon.isEmpty !== 'function' || icon.isEmpty()) {
    throw new Error('Tray icon is empty.')
  }

  const tray = new Tray(icon)
  const show = () => showMainWindow(getMainWindow())
  let menuTemplate = []
  let menu = null
  let destroyed = false

  const rebuild = () => {
    menuTemplate = [
      { label: '显示主窗口', click: show },
      { label: '显示墨团', click: showPet },
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
  tray.on('click', show)
  tray.on('double-click', show)

  return {
    tray,
    get menu() { return menu },
    get menuTemplate() { return menuTemplate },
    show,
    rebuild,
    destroy() {
      if (destroyed) return
      destroyed = true
      tray.destroy()
    },
  }
}
