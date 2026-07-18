# 墨团应用图标实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 Windows 主程序、安装器、卸载器、快捷方式和运行窗口图标统一为项目内置墨团形象。

**Architecture:** 从墨团 spritesheet 的 idle 首帧生成一个透明 512×512 PNG 和一个 16–256px 多尺寸 ICO。Electron 主进程显式加载 PNG，Electron Builder 与 NSIS 使用 ICO，并通过二进制结构测试和最终 EXE 图标提取验收。

**Tech Stack:** Electron 32、electron-builder 25、Node.js test runner、Python Pillow、NSIS。

---

### Task 1: 锁定应用图标契约

**Files:**
- Create: `electron/app-icon.test.mjs`
- Modify: `package.json`

- [ ] **Step 1: 写入失败测试**

测试读取 `package.json`、`electron/main.mjs`、PNG 和 ICO，断言 Windows/NSIS/BrowserWindow 均引用墨团图标，PNG 为 512×512 RGBA，ICO 尺寸集合为 16、24、32、48、64、128、256，并且常规 `npm test` 包含本测试。

- [ ] **Step 2: 验证 RED**

Run: `node --test electron/app-icon.test.mjs`
Expected: FAIL，原因是 `app-icon.png`/`app-icon.ico` 和配置尚不存在。

### Task 2: 生成并接入墨团图标

**Files:**
- Create: `electron/assets/app-icon.png`
- Create: `electron/assets/app-icon.ico`
- Modify: `electron/main.mjs`
- Modify: `package.json`

- [ ] **Step 1: 生成图标资源**

使用 Pillow 从 `electron/pets/motuan/spritesheet.webp` 裁切 `(0,0,192,208)`，再按 alpha bbox `(39,53,160,191)` 裁出墨团，等比缩放到最长边 432px 并居中到透明 512×512 画布；从主图写入 16、24、32、48、64、128、256px ICO 图层。

- [ ] **Step 2: 写入最小配置**

`package.json` 的 `build.win.icon` 指向 `electron/assets/app-icon.ico`，`signAndEditExecutable` 设为 `true`；`build.nsis.installerIcon` 和 `uninstallerIcon` 指向同一 ICO。`electron/main.mjs` 的主 BrowserWindow 使用 `app-icon.png`。

- [ ] **Step 3: 验证 GREEN**

Run: `node --test electron/app-icon.test.mjs`
Expected: PASS。

- [ ] **Step 4: 运行 Electron 全量测试**

Run: `npm test`
Expected: Electron/Node 与 Vitest 全部通过。

### Task 3: 重新打包并验收 Windows 图标

**Files:**
- Modify: `release/win-unpacked/**`
- Modify: `release/智学协作台 Setup 1.0.0.exe`
- Modify: `codex/AI模型任务队列.md`

- [ ] **Step 1: 构建和打包**

Run: `npm run desktop:pack`
Expected: `release/win-unpacked/智学协作台.exe` 生成且退出码 0。

Run: `npm run desktop:dist`
Expected: `release/智学协作台 Setup 1.0.0.exe` 生成且退出码 0。

- [ ] **Step 2: 验证最终资源**

从 unpacked EXE 提取关联图标到隔离临时目录，确认不是 Electron 默认图标并与墨团主图视觉一致；核对安装包版本、大小和 SHA-256。

- [ ] **Step 3: 验证运行生命周期**

运行隔离桌面测试模式，要求退出码 0、tray/backend ready/backend stop/test-mode exit 标记 4/4、残留进程 0。

- [ ] **Step 4: 更新队列并提交**

把 S-038 标记为完成，记录图标哈希、安装包哈希、测试和生命周期证据；执行 `git diff --check` 后提交。
