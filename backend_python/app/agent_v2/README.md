# Agent v2 — Per-User Chatbot

v0.1 全面重写了旧的 LangGraph agent，去掉状态机复杂度，回归「每个用户一个聊天机器人」的核心场景。

## Tech Stack

| 层 | 选型 | 说明 |
|---|------|------|
| 框架 | FastAPI | 复用项目现有框架 |
| 异步DB | SQLAlchemy 2.0 async + asyncmy + MySQL | 与项目一致 |
| LLM | LangChain ChatOpenAI → DeepSeek API | `stream_usage=True` 拿精确 token 数 |
| 流式 | SSE via sse-starlette | 服务端流式推送 |
| 前端 | Vue 3 + TypeScript | SSE 逐行解析拼回文本 |
| 认证 | JWT (get_current_user) | 与项目现有认证一致 |

## 功能

- **POST /agent/create** — 新建空对话，返回 `thread_id`
- **POST /agent/delete** — 删除对话及其所有消息，校验所有权
- **POST /agent/conversations** — 列出用户的对话（游标分页，按 updated_at 降序）
- **POST /agent/history** — 查看对话消息历史（游标分页，按 id 升序）
- **POST /agent/chat** — SSE 流式聊天。无 thread_id 自动新建对话。首条消息自动截 50 字设为标题

## 数据模型

```sql
-- 对话表
agent_v2_conversations
  id            INT PK AUTO
  thread_id     VARCHAR(64) UNIQUE   -- UUID hex
  account_id    INT NOT NULL         -- 用户隔离
  title         VARCHAR(255)         -- 首条消息自动填充
  created_at    DATETIME
  updated_at    DATETIME
  INDEX (account_id, updated_at)     -- 列表排序

-- 消息表
agent_v2_messages
  id                BIGINT PK AUTO
  thread_id         VARCHAR(64)       -- FK 逻辑关联 conversation
  account_id        INT NOT NULL      -- 冗余字段，隔离用
  role              VARCHAR(16)       -- user / assistant
  content           TEXT
  model             VARCHAR(64)       -- 仅 assistant 有值
  prompt_tokens     INT               -- LLM 输入 token 数
  completion_tokens INT               -- LLM 输出 token 数
  total_tokens      INT               -- 总和
  duration_ms       INT               -- LLM 调用耗时
  created_at        DATETIME(3)
  INDEX (thread_id, id)              -- 历史查询
  INDEX (account_id, id)             -- 隔离查询
```

## 架构分层

遵循项目约定：**Router → Service → Repo → SQLAlchemy Model**

```
app/agent_v2/
├── __init__.py
├── schemas.py    Pydantic 请求/响应模型
├── repo.py       唯一 import SQLAlchemy Model 的层，操作 dict
├── service.py    编排逻辑，操作 dict/primitives，不碰 Model
├── router.py     FastAPI 端点，依赖注入
├── deps.py       依赖注入工厂
└── README.md     本文档
```

## 依赖注入模式

**两种模式，按是否需要流式区分：**

### 非流式端点（create / delete / conversations / history）

```
router → Depends(get_db) → ChatService(db) → AgentV2Repository(db)
```

完整链路：`get_db()` 开 session → 注入 router → 传进 service → 传进 repo → 路由返回后 `get_db()` 自动 commit/rollback。与项目其他模块完全一致。

### 流式端点（chat）

Chat 的生命周期横跨 generator，`get_db()` 会在路由 return 后立即退出，无法覆盖 generator 阶段。因此 stream 相关的四个 service 方法各自开闭独立 session：

```
service.setup_thread()       → async with AsyncSessionLocal() + commit
service.save_user_message()  → async with AsyncSessionLocal() + commit
service.prepare_context()    → async with AsyncSessionLocal() (只读)
service.save_response()      → async with AsyncSessionLocal() + commit
```

四个 session 互不共享，用完即还，不跨 generator 持有连接。

## Chat 主链路

```
用户输入 "给我推荐热门视频"
         │
         ▼
router.chat()
  ├─ service.setup_thread()         → 校验/新建对话，返回 thread_id
  ├─ service.save_user_message()    → 存 user 消息 + 空标题自动填充
  ├─ service.prepare_context()      → 加载最近 20 条消息，转 LangChain 格式
  │
  ├─ llm.astream(context)           → 逐 token astream
  │     └─ yield {"event": "token", "text": "推"}  → SSE 推送前端
  │     └─ yield {"event": "token", "text": "荐"}  → SSE 推送前端
  │     └─ ...
  │
  ├─ service.save_response()        → 存 assistant 消息 + token/duration 指标
  │
  └─ yield {"event": "done"}        → 前端收起流，更新对话列表
```

## 评价指标

每条 assistant 消息自带：

- `model` — 所用模型名
- `prompt_tokens` — 输入 token 数
- `completion_tokens` — 输出 token 数
- `total_tokens` — 总和
- `duration_ms` — LLM 调用耗时

来源：`ChatOpenAI(stream_usage=True)` 流结束的最后一个 chunk 携带 `usage_metadata`，配合 `time.time()` 计算耗时。

可基于 message 表按对话/用户/时间聚合统计分析。

## 遇到的困难 & 解决方案

### 1. SSE generator 与 DB session 生命周期冲突

困难：`EventSourceResponse(generator())` 在路由 return 时立即返回 HTTP 响应，`get_db()` 随之退出 commit/close。generator 真正开始运行后，session 已不可用。

方案：流式相关方法各自独立开 session（`async with AsyncSessionLocal()`），不依赖 `get_db()`。非流式端点仍用标准 `Depends(get_db)`。

### 2. LangChain stream_usage 拿到精确 token 数

ChatOpenAI 的 `stream_usage=True` 会在 `astream()` 最后一个 chunk 上附加 `usage_metadata`，包含 `input_tokens` / `output_tokens` / `total_tokens`。生成器结束时取 `last_chunk.usage_metadata` 即可。

### 3. 首条消息自动命名

`save_user_message()` 存完用户消息后检查 `conversation.title`，为空则截取用户消息前 50 字设为标题。一次操作，不需要额外的 LLM 调用。

## 与 v0 的对比

| 维度 | v0 (LangGraph) | v0.1 (直连) |
|------|----------------|-------------|
| 状态机 | 5 节点 LangGraph + classifier/L0/L1/L2 | 无，直接 `llm.astream()` |
| 工具 | 13 个 tools + 安全门 + human-in-the-loop | 纯聊天，无工具 |
| 记忆 | Redis 工作记忆 + ZSET 短期 + MySQL 长期 | MySQL 最近 20 条消息 |
| 评价 | 50+ 行 eval 逻辑 | 每个 message 自带 token/duration 字段 |
| 文件数 | 10+（含 memory/、safety、models 等） | 5 个 |
| 核心代码 | ~1100 行 | ~400 行 |

## 后续维护要点

- 加新功能时遵守分层：router 不写 DB 逻辑，service 不引 Model，repo 只返回 dict
- 非流式端点用 `Depends(get_db)`，流式端点 service 自己管理 session
- 加新模型时记得在 `main.py` 的 import list 和 `models/__init__.py` 里注册
- `deps.py` 放依赖注入工厂，保持整洁
