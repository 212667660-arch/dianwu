# Desktop Pet Character Import and Audio Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为现有 Electron 桌宠增加安全角色包导入/恢复默认和动作音效、语音鼓励的独立开关与音量控制。

**Architecture:** 主进程新增纯逻辑角色导入器并通过固定 IPC 控制系统目录选择和热重载；桌宠 renderer 新增可测试的本地音频策略与 Web Audio/speechSynthesis 适配器；Vue 设置卡只操作脱敏设置与固定 bridge。

**Tech Stack:** Electron 32、Node test runner、Vue 3、Vitest、Web Audio、Web Speech API、Python Pillow atlas validator。

---

### Task 1: 扩展声音设置契约

**Files:**
- Modify: `electron/pet-config.mjs`
- Modify: `electron/pet-config.test.mjs`
- Modify: `electron/ipc-contract.mjs`
- Modify: `electron/ipc-contract.test.mjs`

- [ ] 在测试中要求旧设置补默认值，并只接受 `soundEnabled/voiceEnabled` 布尔值与 `0/0.25/0.5/0.75/1` 音量。
- [ ] 运行 `node --test electron/pet-config.test.mjs electron/ipc-contract.test.mjs`，确认新字段未实现而失败。
- [ ] 新增 `PET_VOLUME_VALUES`、默认设置合并与固定 IPC 校验。
- [ ] 重跑聚焦测试并提交。

### Task 2: 本地声音运行时

**Files:**
- Create: `electron/pet/pet-audio.js`
- Create: `electron/pet-audio.test.mjs`
- Modify: `electron/pet/pet-renderer.js`
- Modify: `electron/pet-renderer.test.mjs`

- [ ] 测试 `audioCueForState`、点击/双击音效、waiting/failed 语音、30 秒冷却、重复状态去重、隐藏与关闭取消。
- [ ] 运行 `node --test electron/pet-audio.test.mjs electron/pet-renderer.test.mjs`，确认模块缺失。
- [ ] 实现纯策略与 `createPetAudioRuntime({AudioContext,speechSynthesis,SpeechSynthesisUtterance})`，音效和语音独立读取音量。
- [ ] renderer 在交互和状态变更时调用运行时，visibility/settings 变化时停止对应通道。
- [ ] 重跑测试并提交。

### Task 3: 角色包安全导入器

**Files:**
- Create: `electron/pet-character-import.mjs`
- Create: `electron/pet-character-import.test.mjs`
- Modify: `electron/pet-controller.mjs`
- Modify: `electron/pet-controller.test.mjs`

- [ ] 使用临时目录测试合法导入、非法清单、超限文件、符号链接、atlas 几何/透明错误、失败不覆盖和恢复默认。
- [ ] 运行聚焦 Node 测试确认失败。
- [ ] 实现 `createPetCharacterImporter`，只从主进程选择的目录读取两个固定文件，staging 校验后原子替换。
- [ ] 控制器新增 `reloadPet()`，只重建宠物窗口，不清除主 renderer sender。
- [ ] 重跑测试并提交。

### Task 4: 固定 IPC 与主进程接线

**Files:**
- Modify: `electron/main.mjs`
- Modify: `electron/preload.cjs`
- Modify: `electron/runtime.test.mjs`
- Modify: `package.json`

- [ ] 先扩展 runtime 测试，要求 `petChooseCharacter/petResetCharacter` 固定 bridge 和主进程 importer 接线，不允许 renderer 路径。
- [ ] 运行 `node --test electron/runtime.test.mjs` 确认失败。
- [ ] 主进程使用 `dialog.showOpenDialog({properties:['openDirectory']})`，导入成功后 `reloadPet()`；取消返回原快照。
- [ ] 恢复默认只删除受控 current 目录并热重载。
- [ ] 把新增 Node 测试加入 `npm test` 并重跑 Electron 测试。

### Task 5: 前端 API 与书桌卡

**Files:**
- Modify: `src/api/types.ts`
- Modify: `src/api/transport.ts`
- Modify: `src/api/backend.ts`
- Modify: `src/api/backend.test.ts`
- Modify: `src/components/pet/PetSettingsCard.vue`
- Modify: `src/components/pet/PetSettingsCard.test.ts`

- [ ] Vitest 要求两个独立声音开关/音量、导入、恢复默认、Web 禁用与错误展示。
- [ ] 运行聚焦 Vitest 确认失败。
- [ ] 扩展 `PetSettings`、固定 bridge API 和卡片 UI；音量选择不修改 speed。
- [ ] 重跑聚焦测试与完整 Vitest。

### Task 6: 打包、桌面验收与文档

**Files:**
- Modify: `README.md`
- Modify: `a3-front/a3-front/src/api/README.md`
- Modify: `codex/AI模型任务队列.md`

- [ ] 运行完整 `npm test`、atlas validator、`npm run build:desktop`、`npm run desktop:pack` 和 `git diff --check`。
- [ ] unpacked 验证声音设置独立持久化、语音默认关闭、导入合法测试包、非法包不覆盖、恢复墨团和进程退出。
- [ ] 更新文档与队列，记录未完成的主观音色/许可证 QA。
- [ ] 提交当前分支，不 merge、不 push。
