# S-003 真实 SSE 流式编排与取消机制

## 1. 目标

把当前“完整生成后按 12 字切片”的伪流式改为上游模型分片直传，同时保证协议校验、数据库一致性、客户端断开、超时和错误事件可控。

## 2. 当前问题

- profile_agent 和 resource_agent 先生成完整文本，用户等待时间没有真正缩短。
- get_chat_reply_stream 未被实际 Agent 流程使用。
- 同步 OpenAI 客户端在 async 路由中可能阻塞事件循环。
- StreamingResponse 生成器没有检查客户端断开，也没有取消上游请求。
- 内容在流式返回前已写库，客户端断开仍可能留下用户未看到的结果。

## 3. 分层设计

### ModelGateway

- 使用 AsyncOpenAI 或混元兼容的异步客户端。
- 提供 complete(messages, options) 和 stream(messages, options)。
- stream 返回异步文本分片，不包装业务事件。
- 统一超时、重试、异常映射和上游连接关闭。

### AgentRunner

- 根据 Agent 类型构造提示词。
- 直接消费 ModelGateway.stream，将纯文本分片交给 Orchestrator。
- 同时累积完整原始输出，流结束后交给 Protocol Validator。
- 不访问 HTTP Request，不直接提交数据库事务。

### Orchestrator

- 管理会话状态、request_id、generation_id 和当前 phase。
- 把模型分片转换为领域流事件。
- 检查取消信号和超时。
- 在完整输出校验通过后保存规范文本。
- 失败时恢复 last_stable_state，不覆盖有效画像和资源。

### SSE Adapter

- 把领域事件编码为 SSE。
- 检查 request.is_disconnected。
- 发送心跳，处理客户端取消和生成器清理。
- 不包含 Agent 业务决策。

## 4. SSE 事件协议

每个事件包含递增 id，data 使用 UTF-8 JSON 包装元数据，content 字段保持 Agent 的纯文本分片。

### phase

说明当前阶段。

示例字段：request_id、generation_id、phase、session_state。

phase 枚举：diagnosis、profile、resource、repair、persist。

### delta

上游模型产生的文本分片。

示例字段：request_id、sequence、content、provisional=true。

provisional 表示内容尚未通过完整协议校验。前端可以即时展示，但不应在本地历史中标记为最终结果。

### heartbeat

长时间无分片时每 15 秒发送一次，避免代理和浏览器误判连接失效。

### validation

完整输出校验结果。

字段：valid、protocol、version、repair_attempted、error_code。

### replace

若一次修复后得到规范文本，前端用完整 canonical_content 替换此前 provisional 内容。正常校验通过时不发送。

### persisted

数据成功持久化后发送，字段包含 resource_id 或 profile_version。

### error

字段：code、message、retryable、phase、request_id。不得包含 API Key、完整提示词或上游响应原文。

### done

最后一个事件。字段：status=completed、failed 或 cancelled，以及最终 session_state。

## 5. 正常执行顺序

1. 校验请求并创建 request_id。
2. 检查会话状态和并发锁。
3. 发送 phase 事件。
4. 启动上游异步流，逐块发送 delta，同时累积原文。
5. 上游结束后执行协议解析和校验。
6. 校验失败时最多进行一次 repair；成功则发送 replace。
7. 开启短数据库事务，保存规范文本和状态。
8. 发送 persisted。
9. 发送 done，并释放会话锁和上游连接。

## 6. 持久化时机

- 用户消息在模型调用前保存，确保诊断上下文可恢复。
- provisional 模型分片不逐块写入主资源表。
- 完整且校验成功的画像或资源才写入正式表。
- 可选 GenerationTask 表保存任务状态、错误代码和耗时，不保存未验证的完整敏感输出。
- 客户端断开时默认不保存未完成资源；如果上游已经完成且校验成功，可以完成事务，但任务标记 client_disconnected=true。

## 7. 取消与断开

- SSE Adapter 每次发送前检查 request.is_disconnected。
- 发现断开后设置 cancel_event，Orchestrator 停止消费模型流。
- ModelGateway 在 finally 中关闭上游流。
- 任务状态更新为 cancelled，恢复 last_stable_state。
- 不发送后续事件，不保存未完成资源。
- Electron 主动取消时使用 generation_id 调用 DELETE /api/generations/{id}，与断开使用同一取消机制。

## 8. 超时与重试

- 连接超时：10 秒。
- 首分片超时：30 秒。
- 分片空闲超时：30 秒。
- 单次完整生成上限：180 秒，可通过配置调整。
- 流开始前的连接错误可以自动重试。
- 已向用户发送 delta 后不得静默重启整次生成，以免重复内容；应发送 error 并让用户明确重试。

## 9. 并发与幂等

- 每个生成请求携带 request_id；客户端重试相同 request_id 时返回已有任务状态。
- 同一 session 同时只允许一个会改变状态的生成任务。
- 不同 session 可以并行执行。
- 使用 GenerationTask 唯一约束或进程内锁加数据库状态双重保护。
- Electron 单机版本可以先使用进程内 asyncio.Lock 映射，仍需数据库状态防止异常退出后永久占用。

## 10. 前端处理规则

- phase 更新界面阶段提示。
- delta 追加到临时缓冲区。
- replace 清空临时缓冲区并替换为规范文本。
- persisted 后才把内容加入正式历史记录。
- error 显示可重试提示；不得把错误消息混入学习笔记正文。
- done 负责关闭加载状态，不能只依赖连接关闭。

## 11. 测试场景

- 模型正常分片并通过协议校验。
- 模型输出需一次修复，前端收到 replace。
- 首分片超时。
- 已发送部分 delta 后上游断开。
- 客户端主动断开，确认上游取消且无正式资源。
- 数据库保存失败，确认发送 error 且状态恢复。
- 同一 session 并发两个生成请求，第二个被拒绝。
- 相同 request_id 重试不会重复生成和写库。
- 心跳期间不污染正文。

## 12. Terra 实现清单

- 将 OpenAI 客户端改为异步客户端。
- 新建 ModelGateway、AgentRunner、Orchestrator 和 SSE Adapter。
- 新建 StreamEvent 类型和 SSE 编码器。
- 新建 GenerationTask 或等价任务状态模型。
- 从 chat.py 移除 _split_chinese 伪流式。
- 加入 request_id、generation_id、取消接口和连接清理。
- 编写断开、超时、校验、修复和幂等测试。

## 13. 验收标准

- 首个 delta 来自模型真实分片，而不是完整文本切块。
- 客户端断开后上游请求可以被取消。
- 未验证或未完成内容不会进入正式画像和资源表。
- 每次流都有 phase、validation、persisted 或 error、done 的清晰生命周期。
- 任意异常都不会让会话永久停留在 GENERATING。
