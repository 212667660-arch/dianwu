# S-037 发布级全栈验收设计

## 发布门槛

- 后端 compileall、全量 pytest、隔离数据启动、健康检查、OCR worker 与 PyInstaller 均成功。
- Electron Node 测试、Vitest、TypeScript、Vite 桌面构建、electron-builder unpacked/NSIS 均成功。
- 真实桌面流程覆盖首次启动、模型可用与不可用、扫描 PDF OCR、引用跳页、批量管理、回收站、演示模式、墨团、托盘完全退出。
- 退出后不存在应用、Electron、api.exe 或知识 worker 残留进程。
- 日志无密钥、令牌、请求正文或用户原始路径泄露。

## 证据

所有命令、测试计数、安装包路径、真实文件摘要、进程检查和已知限制写入任务队列完成记录；任何一项失败都保持 S-037 为待验证或阻塞，不作完成声明。
