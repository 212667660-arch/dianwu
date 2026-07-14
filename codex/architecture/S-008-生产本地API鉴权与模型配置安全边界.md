# S-008 生产本地 API 鉴权与模型配置安全边界

## 1. 目标

修复后端当前的生产安全缺口：模型配置接口已有局部令牌校验，但聊天、资源、历史、删除、取消和在线检索接口没有统一鉴权；模型 API Key 直接写入 `.env`；自定义 `base_url` 没有限制内网地址。

本设计适用于 A3 的 Windows Electron 桌面版，也兼容本地开发模式。目标是让 renderer 不持有后端令牌和模型密钥，其他本机进程不能无认证调用业务接口或读取、删除学习数据。

## 2. 当前问题与安全等级

| 问题 | 风险 | 处理结论 |
| --- | --- | --- |
| 只有 `/api/settings/model*` 校验 `X-A3-Desktop-Token` | 本机其他进程可以调用聊天、读取历史、删除会话并消耗模型额度 | P0，所有业务路由统一进入鉴权中间件 |
| 模型 API Key 以明文写入 `.env` | 文件读取权限或备份泄露会暴露第三方模型密钥 | P0，生产版使用 Windows DPAPI 或 Electron safeStorage |
| `MODEL_BASE_URL` 可指向任意地址 | 配置接口被滥用时可能访问 localhost 或内网服务 | P1，默认拒绝环回、私有、链路本地和未允许端口 |
| 令牌配置通过环境变量长期存在 | 进程环境、日志或启动脚本可能暴露令牌 | P1，桌面版每次启动随机生成，仅保存在后端内存 |
| 无请求频率限制 | 重复点击或本机恶意程序可持续消耗模型额度 | P1，按 token、IP 和 session 限制高成本接口 |

## 3. 信任模型

```text
Electron renderer
    | 仅调用 preload 暴露的固定 IPC
    v
Electron main process
    | 持有短期 local_token，不把 token 交给 renderer
    | 代理 HTTP/SSE 请求并校验参数
    v
FastAPI backend 127.0.0.1
    | 除 /health/live 外要求 X-A3-Desktop-Token
    | token 只保存在进程内存
    v
模型网关 / SQLite / 公开检索
```

开发模式允许前端直连，但仍需要显式的开发令牌；不能因为绑定 `127.0.0.1` 就认为接口天然安全。绑定本机地址只能降低局域网暴露面，不能阻止本机其他进程访问。

## 4. 令牌生命周期

### 4.1 Electron 生产模式

1. Electron main process 使用密码学安全随机数生成至少 32 字节 token。
2. token 通过受控的进程启动通道传给后端，不放入命令行参数、URL、日志或数据库。
3. 后端启动时读取一次 token，使用常量时间比较保存的摘要。
4. 每次应用启动都生成新 token，应用退出后旧 token 立即失效。
5. main process 代理所有业务请求，在 renderer 侧不暴露 token。
6. 后端只接受 `127.0.0.1` 或 `::1` 的 Host/连接地址。

### 4.2 开发模式

- `APP_ENV=development` 时允许配置 `DESKTOP_TOKEN`，但仍要求业务请求携带该 token。
- 为方便 Swagger 和人工调试，可以提供显式的开发启动命令生成临时 token。
- 不允许生产环境使用空 token 放行。
- `/health/live` 可以无 token；`/health/ready` 默认要求 token。

## 5. FastAPI 实现边界

新增一个 HTTP middleware 或依赖项，覆盖以下路由：

| 路由 | 生产要求 |
| --- | --- |
| `/health/live` | 无 token，仅返回存活状态 |
| `/health/ready` | 要求 token；启动握手使用内部请求头 |
| `/api/chat*` | 必须 token |
| `/api/profile` | 必须 token |
| `/api/resource` | 必须 token |
| `/api/web/search` | 必须 token，并限流 |
| `/api/sessions*` | 必须 token，并校验 session 归属 |
| `/api/generations/*` | 必须 token，并校验 generation 归属 |
| `/api/settings/model*` | 必须 token |

鉴权失败统一返回：

```json
{
  "code": "DESKTOP_AUTH_REQUIRED",
  "message": "本地桌面请求未通过授权。",
  "retryable": false,
  "request_id": "..."
}
```

不要在错误中说明 token 是否只差一部分，也不要回显请求头。

## 6. generation 与 session 归属

当前取消接口只按 `generation_id` 查找内存事件。实现统一鉴权后还需要绑定客户端归属：

- 创建 generation 时记录 `generation_id -> session_id` 和启动 token 的短期指纹。
- 取消请求必须同时满足 token 有效、generation 存在且属于当前客户端。
- 应用退出时清空 generation 映射。
- generation 完成、失败或取消后立即删除映射。
- 不把完整 token 写入日志。

## 7. 模型密钥存储

### 7.1 生产版

推荐由 Electron main process 使用 `safeStorage` 保存：

- `settings.enc` 只存加密后的 provider、base_url、model_name、API Key 和超时。
- renderer 只提交一次性表单数据给 main process。
- 后端通过受保护的本地启动通道或内存配置接口得到密钥。
- 后端退出时不把密钥写回 `.env`。
- API 响应只返回 `api_key_configured` 和脱敏 hint，不返回原文。

如果暂时只交付 Python 后端，应提供 Windows DPAPI/Credential Manager 适配器；开发环境可以继续使用 `.env`，但启动时必须检查文件权限并给出明确警告。

### 7.2 密钥变更

- 更新配置前先调用连接性检测，但连接性检测不能把完整模型回答写入日志。
- 新配置验证成功后再替换当前配置。
- 替换失败保留旧配置，不产生半写入 `.env`。
- 使用临时文件加 `replace` 做原子保存；不在日志输出密钥内容。

## 8. 自定义网关地址校验

默认允许：

- `https://` 公网地址。
- 明确配置的开发测试域名。
- `http://127.0.0.1` 仅在 `APP_ENV=development` 且显式启用本地网关时允许。

默认拒绝：

- `file://`、`data://`、`javascript://` 等非 HTTP(S) 协议。
- `127.0.0.0/8`、`::1`、`0.0.0.0`。
- RFC1918 私网、链路本地、IPv6 本地地址。
- DNS 解析后落入上述地址的域名。
- 非必要端口和带用户密码的 URL。

校验需要在保存配置和实际请求前分别执行，防止 DNS rebinding。生产版优先使用域名白名单；确需私有模型服务时使用显式网段白名单。

## 9. 限流与资源保护

最低要求：

- `/api/chat`、`/api/chat/stream`、`/api/profile`、`/api/resource`：同一 token 每分钟不超过 10 次。
- `/api/web/search`：同一 token 每分钟不超过 30 次。
- 同一 session 同时只允许一个生成任务。
- 请求体和历史上下文同时受字符数与估算 token 数限制。
- 取消、失败和超时任务不应继续占用生成槽位。

超限统一返回 `429 REQUEST_RATE_LIMITED`，并带 `Retry-After`，不泄露内部计数。

## 10. 测试矩阵

必须增加以下测试：

1. 无 token 访问每个业务路由均返回 401/403，`/health/live` 仍返回 200。
2. 错 token、过期 token、旧启动 token 均不能访问业务路由。
3. 合法 token 可以访问普通聊天、SSE、资源、历史、导出、搜索和取消。
4. generation A 的 token 不能取消 generation B。
5. 应用关闭后旧 token 和旧 generation 均失效。
6. 生产配置拒绝 localhost、私网和危险协议 base_url。
7. API Key 不出现在响应、日志、异常、命令行和导出内容中。
8. 密钥更新失败时旧配置仍可用，文件不会出现半写入内容。
9. 超过限流阈值返回 429，正常请求在窗口恢复后可继续执行。
10. 真实模型 401、403、404、429 和 SSE 断流都返回统一错误事件。

## 11. Terra 实现清单

- 新增统一 `DesktopTokenMiddleware` 或等价依赖，默认保护全部 `/api` 路由。
- 将 `/health/live` 设为唯一匿名接口，明确 readiness 启动握手策略。
- 将模型配置保存从明文 `.env` 抽象为 `CredentialStore`，开发版和 Windows 生产版分别实现。
- 新增 `base_url` scheme、DNS/IP 和环境白名单校验。
- 为 generation 增加归属映射和生命周期清理。
- 补充 SSE 403/404/未知异常的统一错误事件。
- 为高成本路由加入按 token/session 的限流。
- 增加上述测试矩阵，并重新构建 `api.exe`。

## 12. 验收标准

- 没有 token 的本机请求不能访问任何业务 API。
- renderer 不接触 token 和 API Key。
- API Key 不以明文写入生产配置文件。
- 自定义网关不能默认访问本机或内网地址。
- 模型认证、权限、模型不存在、限流和网络失败均能通过普通响应或 SSE 得到结构化错误。
- 旧功能测试全部通过，打包版可以完成健康检查、诊断、资源生成、历史和取消。
