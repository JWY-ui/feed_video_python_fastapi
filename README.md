# 短视频平台 · Python 后端 + 站内 AI 助手

一个完整的短视频社区服务端：Feed、点赞、评论、关注、私信、通知、标签、分片上传，
外加一个**能替你操作站内功能、但写操作必须经你确认**的 AI 助手。

> **规模**：后端 Python 约 6600 行（其中助手 1760 行，业务后端 4879 行）
> + 前端 TypeScript/Vue 约 5100 行；**44 个业务接口 + 6 个助手接口**；
> 20 个 AI 工具；**95 项自动化测试**。

## 目录

- [快速开始](#快速开始)
- [项目结构](#项目结构)
- [第一部分 · 站内 AI 助手](#第一部分--站内-ai-助手)
- [第二部分 · 短视频平台后端](#第二部分--短视频平台后端)
- [接口一览](#接口一览)
- [已知缺口](#已知缺口)

---

# 快速开始

## 前置要求

| | 版本 | 是否必需 |
|---|---|---|
| Python | 3.10+（Docker 镜像用 3.12） | 必需 |
| MySQL | 8.0 | 必需 |
| Redis | 7 | **可选** —— 连不上会自动降级，见下方「后端亮点 ①」 |
| Node.js | 22+（仅前端需要） | 可选 |
| Docker + Compose | —— | 仅方式一需要 |

## 方式一：Docker Compose（一条命令起全栈）

```bash
cd backend_python
docker compose up -d --build
```

起四个容器，`depends_on: service_healthy` 保证 MySQL / Redis 就绪后才启动后端：

| 服务 | 地址 | 说明 |
|---|---|---|
| 前端（Nginx） | http://localhost | 构建后的 Vue 产物 + `/api` 反代 |
| 后端 | http://localhost:8080 | 接口与 `/docs` |
| MySQL | localhost:3307 | 映射到容器内 3306 |
| Redis | localhost:6378 | 映射到容器内 6379 |

> **注意**：`docker-compose.yml` 没有转发 `OPENAI_API_KEY`，所以容器里的
> `/agent/*` 会返回 503（助手不配模型就不可用，没有降级模式）。
> 要用助手，在 compose 的 `backend.environment` 里补上 `OPENAI_API_KEY` 和
> `LLM_BASE_URL`，或在 `backend` 服务下加 `env_file: .env`。

## 方式二：本地开发

### 1. 后端

```bash
cd backend_python

# 依赖装进虚拟环境（Windows 用 .venv\Scripts\activate）
python -m venv .venv && source .venv/bin/activate

# requirements-dev.txt 已经 -r requirements.txt，并带上 pytest
pip install -r requirements-dev.txt

# 复制配置模板，至少改掉 JWT_SECRET 和 MySQL 口令
cp .env.example .env

# 启动（--reload 开发用；生产去掉）
python -m uvicorn app.main:app --reload --port 8080
```

启动时 `lifespan` 会自动完成：建库（若不存）、`create_all` 建表、
对齐 LangGraph checkpoint 表的排序规则、连接 Redis（失败不阻塞）、装配助手。
不用手动跑 migration —— **项目没有用 Alembic**，建表全靠 SQLAlchemy `create_all`。

接口文档：http://localhost:8080/docs （FastAPI 自动生成的 Swagger）。
健康检查：`GET /healthz`。

### 2. 前端

```bash
cd backend_python/frontend
npm install
npm run dev          # http://localhost:5173
```

Vite 会把 `/api/...` 代理到 `http://127.0.0.1:8080/...`（见 `vite.config.ts`）。
前端单独说明见 [`backend_python/frontend/README.md`](backend_python/frontend/README.md)。

### 3. 配置

配置全部走环境变量，读的是 `backend_python/.env.example` 里那些键（环境变量优先于 `.env` 文件）。

| 变量 | 默认 | 说明 |
|---|---|---|
| `SERVER_PORT` | `8080` | 后端监听端口 |
| `MYSQL_HOST` / `MYSQL_PORT` | `localhost` / `3306` | 本地开发时 MySQL 常映射到 3307 |
| `MYSQL_USER` / `MYSQL_PASSWORD` | `root` / `123456` | |
| `MYSQL_DATABASE` | `feedsystem` | 测试用独立的 `feedsystem_test` |
| `JWT_SECRET` | `change-me-to-a-random-string` | **上线必须改** —— 不改启动时会打警告 |
| `REDIS_HOST` / `REDIS_PORT` / `REDIS_PASSWORD` | `localhost` / `6379` / `123456` | 连不上只降级、不报错 |
| `OPENAI_API_KEY` | 空 | **空 = `/agent/*` 全部返回 503** |
| `LLM_BASE_URL` | `https://api.deepseek.com` | OpenAI 兼容端点，可换任意供应方 |
| `LLM_MODEL` | `deepseek-flash` | |
| `AGENT_LLM_MAX_RETRIES` / `AGENT_LLM_TIMEOUT` | `2` / `60` | 单次模型调用的重试与超时（秒） |
| `AGENT_MAX_TOOL_TURNS` | `8` | 单轮最多工具调用次数 |
| `AGENT_MAX_CONTEXT_TOKENS` | `12000` | 上下文 token 预算 |

### 4. 跑测试

```bash
cd backend_python
python -m pytest
```

95 项测试，**走独立的 `feedsystem_test` 库**，不碰开发库（见 `tests/conftest.py`）。
需要 MySQL 可连通；Redis 不是必需。

---

# 项目结构

```
backend_python/
├── app/
│   ├── main.py              # FastAPI 入口：lifespan、路由注册、限流装配
│   ├── config.py            # pydantic-settings 读环境变量
│   ├── database.py          # async engine / session
│   ├── dependencies.py      # get_db / get_current_user / get_optional_user
│   │
│   ├── routers/             # HTTP 层：只做参数校验与调用 service
│   ├── services/            # 业务编排：从不 import ORM Model
│   ├── repositories/        # 数据访问：唯一接触 ORM 的地方，只返回 dict
│   ├── models/              # SQLAlchemy ORM
│   ├── schemas/             # 请求 / 响应 DTO
│   │
│   ├── middleware/
│   │   ├── jwt_auth.py      # 认证依赖
│   │   └── rate_limit.py    # Lua + ZSET 滑动窗口限流
│   ├── utils/
│   │   ├── redis_client.py  # 手写封装，"可选依赖"的实现（全项目最大文件，288 行）
│   │   ├── timeutil.py      # naive-UTC 读写约定收口
│   │   ├── sql.py           # escape_like 等
│   │   ├── tag_parser.py    # #标签 / @提及 抽取
│   │   ├── jwt_helper.py
│   │   └── password.py      # bcrypt
│   │
│   └── agent_v3/            # 站内 AI 助手（第一部分）
│       ├── graph.py         # LangGraph 图：agent / confirm / tools 三节点
│       ├── checkpointer.py  # checkpoint 表排序规则对齐
│       ├── service.py       # 会话编排、SSE 流式
│       ├── router.py        # 6 个助手接口
│       ├── context.py       # 上下文裁剪（4KB / token 预算）
│       ├── deps.py          # 服务装配与生命周期
│       ├── repo.py          # 会话表数据访问
│       └── tools/           # 20 个工具，按域分 5 个模块 + registry.py
│
├── frontend/                # Vue 3 + TypeScript
│   └── src/
│       ├── api/             # 各域 API 客户端 + SSE 客户端
│       ├── components/      # 含 AgentPanel.vue（悬浮助手）
│       ├── views/           # 11 个页面
│       ├── stores/          # Pinia
│       └── utils/           # 含 time.ts、uiActions.ts
│
├── tests/                   # 95 项测试
│   ├── conftest.py          # 独立测试库 + 每个测试后释放连接池
│   ├── factories.py         # 造数据
│   └── agent_v3/            # 助手测试（含桩模型、并发、持久化）
│
├── docker-compose.yml       # MySQL + Redis + 后端 + Nginx 前端
├── Dockerfile
├── requirements.txt         # 生产依赖
└── requirements-dev.txt     # + pytest
```

一条贯穿全项目的强约定：**repository 是唯一 import ORM Model 的地方，且只返回
`dict` / 原始类型**，上层永远看不到 ORM 对象；service 层从不 import Model。
详见[后端 · 分层与约定](#分层与约定)。

---

# 第一部分 · 站内 AI 助手

## 它是什么

应用右下角的悬浮助手：能找视频、看评论、查关注和私信，也能**替你发私信、发评论**。
核心约束是 —— **读操作直接执行，对外可见的写操作必须先弹确认卡**，用户点了才真的发出去。

## 技术栈

| | |
|---|---|
| 编排 | **LangGraph 1.2.4**（有状态图 + checkpointer + `interrupt()` / `Command(resume=)`） |
| 模型 | langchain-openai → DeepSeek（OpenAI 兼容协议，可换任意兼容端点） |
| 状态持久化 | **langgraph-checkpoint-mysql[asyncmy]** —— 复用项目已有的 asyncmy 驱动，不引入第二个 MySQL 驱动 |
| 服务端 | Python 3.10 / FastAPI / SQLAlchemy 2.0 async / MySQL 8 / **SSE** |
| 前端 | Vue 3 + TypeScript + Pinia；手写 SSE 客户端（`fetch` + `ReadableStream`） |

## 怎么设计的

### 图骨架

```
START → agent ─┬─(有 write_public)──→ confirm ──→ tools → agent …
               ├─(只有读 / 可逆写)───→ tools ──→ agent …
               └─(没有工具调用)──────→ END
```

`agent` 调模型、`tools` 执行工具、`confirm` 在需要用户拍板时挂起。

### 四个关键取舍

**1. 写操作确认用动态 `interrupt()`，而不是静态 `interrupt_before`。**
静态断点无法把"用户点了同意还是取消"传回节点；动态 `interrupt()` 的返回值就是
`Command(resume=...)` 带回来的决定，`confirm` 节点因此能真正参与决策。
代价是：`interrupt()` 恢复时节点会**从头重跑**，所以该节点在 `interrupt()` 之前
只能做无副作用的准备 —— 真正的写操作必须放在它之后的 `tools` 节点。

**2. 单源真相：transcript 只存一份。**
消息交给 checkpointer 持有，另建一张**薄会话表**（`thread_id / account_id / title`）
只负责归属校验和侧栏排序。不双写消息表 —— 两套副本必然漂移，而这正是本项目
已经踩过的一类 bug。

**3. 三级工具权限**，级别决定要不要打断用户：

| 级别 | 行为 | 工具 |
|---|---|---|
| `read` | 直接执行 | `search_videos`、`list_comments`、`search_user`… |
| `write_reversible` | 直接执行（有反向操作、影响面小） | `like_video`、`follow_user` |
| `write_public` | **必须用户确认** | `send_message`、`publish_comment` |

共 **20 个工具**，分 feed / social / content / message / account 五个域，
每个域一个模块，注册表统一带 `tier`。

**4. 身份不走模型。**
`account_id` / `username` 由服务端在图启动时注入 state，模型只能产出 `messages`
—— 提示注入无法借工具参数提权。

### UI 同步：助手操作时页面跟着走

工具可以返回 `ui` 指令（例如"跳转到与某人的私信页"）。两道防线：

1. `ui` **必须由服务端工具代码构造**，模型无法产出；
2. 前端再用白名单校验一次路径（只接受 `/` 开头且非 `//`，防协议相对 URL 的开放重定向）。

同一轮内多个跳转只取**最后一个**（last-win），避免模型调三个工具就把用户连拽三次。

## 亮点 · 难在哪里、怎么解

### ① 并发下的重复写操作 —— 实测会发出两条私信

压测发现：同一个会话上两个「确认」同时到达时，**写操作会执行两遍**（实测 `executions = 2`）。
根因是同一个 `thread_id` 上没有任何串行化，两个图运行同时读写同一份 checkpoint。

修法：每个会话一把锁（用 `WeakValueDictionary` 持有，不随会话数堆积）+
`/confirm` **幂等**（锁内先查是否还有待确认的 interrupt，没有就直接返回 done）。

> 实测：修复前 2 次 → 修复后 **1 次**。

同一根因还藏着两个更隐蔽的问题，一并修掉：

| 问题 | 实测现象 |
|---|---|
| 同一会话并发两轮对话 | **其中一轮的消息被静默丢弃**，checkpointer 还报 `Duplicate entry ... checkpoint_writes.PRIMARY` |
| 确认卡开着时又发一条消息 | 那次**待确认操作被静默销毁** —— 用户随后点「发送」，写操作一次都不执行，且没有任何报错 |

三个都先写失败的测试再修，现在是回归测试的一部分。

### ② 一个只有真实 checkpointer 才暴露的 bug

`langgraph-checkpoint-mysql` 的 SQL 里有一句：

```sql
json_table(json_keys(checkpoint, '$.channel_versions'), '$[*]'
           columns (channel VARCHAR(150) CHARACTER SET utf8mb4 PATH '$'))
```

这个派生列**只声明了字符集、没写 `COLLATE`**，于是它取的是字符集默认排序规则
（MySQL 8 上是 `utf8mb4_0900_ai_ci`）；而项目建库时用的是 `utf8mb4_unicode_ci`。
两者都是列级（IMPLICIT）排序规则，一比较 MySQL 直接报 `Illegal mix of collations`。

**内存 checkpointer 根本不走这条 SQL** —— 所以所有桩模型测试全绿，一接上真实
checkpointer 就会在用户发的**第一条消息**上炸。

定位到根因后，在启动时**幂等**地把这几张 checkpoint 表对齐到字符集默认排序规则
（它们只归 checkpointer 使用、不与任何业务表 JOIN，所以对齐是安全的；反过来去改
整个库的默认排序规则会让业务表之间步上同样的后尘）。

### ③ 用桩模型把状态机语义"钉死"

`interrupt` / `resume` 是整个助手最难写、也最容易被后续改动**静默打破**的部分。
做法是不依赖真模型、也不依赖网络：把 LLM 换成一个按脚本返回 `AIMessage` 的桩，
但驱动的是**真实的 LangGraph 图 + 真实 MySQL checkpointer**，然后断言：

- 写操作挂起时**不执行**；
- 批准后才执行；
- 拒绝后不执行，并且**要让模型知道用户拒绝了**；
- 确认状态能跨图实例存活（证明它真的在数据库里，而不是在某个 Python 对象里）。

### ④ 上下文工程

工具结果进上下文前有 **4KB 上限**，且保证裁剪后**仍是合法 JSON** —— 模型收到坏
JSON 只会更容易胡编；历史按 token 预算裁剪；并且**绝不产生孤儿 `ToolMessage`**
（少了配对的 `tool_call_id`，OpenAI 协议会直接报错）。

### ⑤ SSE 不占用数据库连接

助手的长连接走 **stateless 认证**。普通认证依赖（`get_current_user → get_db`）会挂着
一个 DB session 直到响应结束 —— 对 SSE 就是永远。这个坑本项目在通知的 SSE 上踩过一次。

> 实测：**30 路并发对话流期间，普通接口延迟中位 1ms**；MySQL 连接数 1 → 11，不随并发线性增长。

### ⑥ 前端：为什么做成悬浮面板而不是独立页面

面板挂在 `App.vue`、位于 `<RouterView>` **之外**。这样"助手操作时页面自动跳转"才成立：
跳转只换下面的页面，**对话本身不会被卸载**。如果做成独立的 `/agent` 页面，
第一次跳转对话就没了。

---

# 第二部分 · 短视频平台后端

## 它是什么

短视频社区的服务端：沉浸式 Feed（最新 / 最多赞 / 热门 / 关注 / 标签 / 搜索共 6 种）、
点赞、评论、关注、私信、实时通知、标签抽取、分片上传。

## 技术栈

| 层 | 选型 |
|---|---|
| 框架 | **FastAPI 0.119** + Uvicorn（全异步，单 worker） |
| 数据库 | **MySQL 8** / SQLAlchemy 2.0 async / **asyncmy** 驱动 / Alembic 未用（`create_all`） |
| 缓存 | **Redis 7**（`redis[hiredis]`）—— 见下方"可选依赖"设计 |
| 鉴权 | **python-jose**（JWT）+ **bcrypt 5** |
| 实时 | **SSE**（手写流，30s keepalive 注释帧） |
| 部署 | Docker Compose：MySQL + Redis + 后端 + Nginx 前端，带 healthcheck 与 `depends_on: service_healthy` |

## 分层与约定

```
routers/  →  services/  →  repositories/  →  models/
（HTTP）     （业务编排）    （数据访问）       （ORM）
             schemas/ 承载请求/响应 DTO
```

一条贯穿全项目、且**写进注释的强约定**：**repository 是唯一 import ORM Model 的地方，
且只返回 `dict` / 原始类型**，上层永远看不到 ORM 对象；service 层从不 import Model。
这样业务逻辑与持久化细节解耦，也让 service 能被独立测试。

`get_db()` 是 yield 依赖，请求结束自动 commit / 异常 rollback，router 从不手动 commit。

## 亮点 · 难在哪里、怎么解

### ① 把 Redis 做成"可选依赖"，并让降级路径真的能跑

`app/utils/redis_client.py`（288 行，全项目最大文件）是手写的 Redis 客户端封装，
口号写在文件头：**"Redis is an optional acceleration layer, not a hard dependency"**。

连接失败不抛异常，只把 `available` 置 false；然后**每个方法各自返回安全默认值**，
业务代码里不需要写任何 `if redis_available`：

| 调用 | Redis 挂掉时返回 | 语义 |
|---|---|---|
| `get` | `None` | 当作缓存未命中 |
| `set` / `set(nx=True)` | `False` | 当作没拿到锁 |
| `zcard` / `zrevrange` | `0` / `[]` | 当作窗口为空 |
| `incr_with_expire` | `1` | **当作放行**，不误伤真实请求 |

好处是本地开发不起 Redis 也能跑通全链路。

> **代价与现状（如实记录）**：不是所有路径都有回退。**限流在 Redis 不可用时是
> "完全关闭"而不是降级** —— `rate_limit.py` 开头就是 `if not redis_client.available: return`。
> 实测：20 个并发登录请求 → 20 个 401、0 个 429，`/account/login` 的暴力破解防护
> （10 次/分钟）等于不存在。这是已知缺口。

### ② 限流：Lua + ZSET 滑动窗口，一次解决两个经典问题

`app/middleware/rate_limit.py` 把整个 **"清理过期 → 计数 → 判断 → 记录"** 写进一段
Lua 脚本，在 Redis 里原子执行。它同时修掉两个各自独立的问题：

- **`INCR + EXPIRE` 的竞态窗口**：INCR 成功但进程在 EXPIRE 前崩掉，key 永不过期，
  该用户被永久锁死；
- **固定窗口的边界 2× 突发**：第 59 秒打 10 次 + 第 61 秒再打 10 次，两秒内过 20 次。

窗口是"最近 N 秒"而不是"第 N 分钟"，突发上限严格压在 1× 阈值。
member 用 `now:count:随机后缀` 防止同毫秒内 ZADD 互相覆盖。

### ③ Token 缓存：Redis 挂掉时"自愈"回 MySQL

登录/刷新时**双写 MySQL + Redis**；读取时 Redis 优先、未命中则回查 MySQL **并回写缓存**
（`account_repo.py`）。所以 Redis 中途挂掉不会导致所有人掉线，重启后缓存也会自动重建。

另外，**查无此人时写一个 `"REVOKED"` 哨兵值（TTL 60s）** —— 防止用不存在的 account_id
反复打穿到数据库（缓存穿透）。

### ④ 双令牌与刷新：把刷新从全表扫描降到 O(1)

| | 形态 | 有效期 | 可吊销 |
|---|---|---|---|
| Access | JWT（HS256，含 account_id/username） | **15 分钟** | 间接（比对 DB/Redis 中的当前 token） |
| Refresh | **不是 JWT**，`secrets.token_hex(32)` 随机串 | **7 天** | 是（存库，登出/改密即失效） |

刷新流程里有个值得说的设计：客户端把**已过期的 access token 和 refresh token 一起**发过来；
服务端用 `decode_token_skip_expiry` —— **仍然验签名，只跳过 exp 校验** —— 从中取出
account_id，再按主键查库比对 refresh token。

这一步把"拿着 refresh token 去表里全表扫描找用户"优化成了**主键查询 O(1)**，
而且因为仍然验签，伪造的 access token 取不出 account_id。

前端侧，刷新是**单飞（single-flight）**的：并发请求只触发一次刷新，其余等同一个 Promise。
刷新结果刻意做成**三态**而非布尔：

- `refreshed` → 用新 token 重试原请求
- `invalid` → 令牌确实失效，清会话
- `transient` → 网络/5xx，**不清会话**（否则一次网络抖动就把用户登出）

并且登录/注册/改密被排除在自动重试之外 —— 否则密码输错会白白多一次刷新往返，
还可能把另一个标签页里有效的会话清掉。

### ⑤ Feed 热冷分离：用 ZSET 的 watermark 决定走哪条路

最新的全局时间线同时存在于两个地方：Redis ZSET（score = 发布时间毫秒）和
MySQL（`idx_videos_create_time`）。

读取时以 **ZSET 里最旧一条的 score 作为 watermark** 来分流：

- 游标在 watermark 之内（数据还在热区）→ 走 `ZREVRANGEBYSCORE`，纯内存；
- 否则 → 走 MySQL，并用 `create_time <` 游标分页。

热区不够 `limit` 时会**自动拼接冷区数据**，保证分页连续。

ZSET 丢失时的重建做了**单飞**：模块级 `asyncio.Lock` + 双重检查，
只放一个请求去回源 1000 条重建，其余请求等它（防惊群）。
发布视频时写入 ZSET 并按 `ZREMRANGEBYRANK` 裁剪到 1000 条。

### ⑥ 不只是 offset：复合游标分页

列表分页全部用**游标**而不是 `OFFSET`（避免深分页扫描 + 翻页期间数据变动导致重复/漏项）：

| 列表 | 游标 |
|---|---|
| 最新 | `create_time`（毫秒） |
| 最多赞 | 复合 `(likes_count, id)` |
| 热门 | 复合三列 `(popularity, create_time, id)` |
| 关注 | `create_time`（秒） |

复合游标里的 `id` 是 **tiebreaker** —— 没有它，`likes_count` 相同的记录会在翻页边界
反复出现或整批跳过。索引也是按这个顺序建的降序复合索引。

### ⑦ 没有 upsert，幂等怎么做

项目刻意不用 `INSERT ... ON DUPLICATE KEY UPDATE`，重复点赞/重复关注靠
**"先查再插 + `flush()` 捕获 `IntegrityError`"**，并依赖数据库唯一约束
（`likes(video_id, account_id)`、`socials(follower_id, vlogger_id)`）兜底并发。

`flush()` 这一步是刻意的：它让唯一约束在**请求内**就触发，而不是等到响应发出之后
（`get_db` 的 teardown）才报错回滚 —— 否则调用方会收到"注册成功"，而事务其实已经回滚了。
这是一个真实修过的 bug。

计数器的增减用 `func.greatest(x + delta, 0)` 在 SQL 层原子完成并**兜底不为负**。

### ⑧ 视频详情：三层缓存保护

`VideoService.get_detail` 把缓存三个经典故障各防一层：

| 故障 | 防护 |
|---|---|
| **缓存雪崩**（同一时刻集体过期） | TTL 随机化：300s + 随机 0–60s |
| **缓存击穿**（热点 key 过期瞬间打穿到 DB） | `SET NX EX 3` 互斥锁，只放一个请求回源；未拿锁的短暂轮询等待，**超时就直接查 DB**（防锁持有者崩死导致无限等） |
| **缓存穿透**（反复查不存在的 id） | 空值哨兵 `__NULL__`，TTL 60s |

删除视频时主动 `DEL` 缓存保证一致性。

### ⑨ 时区：一个静默偏 8 小时、并破坏分页的 bug

MySQL `DATETIME` 不带时区，项目约定**存 naive UTC 墙钟**。但 Python 读回来是 naive 的，
直接 `.timestamp()` 会被当成本地时间 —— 在 UTC+8 的机器上导出的 epoch **早 8 小时**。

后果不只是显示错：**游标分页被破坏** —— 游标指到了 8 小时前，上一页的最后一条没被排除，
翻页会重复出现第一页的内容。

修法是收口到 `app/utils/timeutil.py` 并定成三条约定：DB 一律 naive UTC；Python 里
"现在"一律 aware UTC（`utc_now()`，而不是 `func.now()`）；从 DB 读回的值在参与任何
时间运算前必须过 `as_utc()`。前端对应 `src/utils/time.ts`（无偏移时间串先补 `Z`）。

### ⑩ Tag 与 @提及：一次编译、去重且保序

`#标签` 和 `@提及` 各用一条预编译正则（`re.UNICODE` 支持中文），抽取后**去重且保留
出现顺序**；@提及额外跳过自己和视频作者（避免作者收到两条重复通知）。

LIKE 通配符转义抽成 `escape_like`：**先转义反斜杠再转义 `%` / `_`**（顺序反了会二次转义），
否则搜 `%` 会匹配整张表。

### ⑪ 分片上传

`/video/chunk/init | upload | status | complete` 四步。客户端 5MB 分片、
**最多 3 片并发**、每片最多重试 3 次；`spark-md5` 流式计算整文件 MD5 和每片 MD5。

服务端按 `file_hash` 复用上传会话：同账号同文件再次 init 会**返回原 upload_id 与已传分片索引**
—— 这是**断点续传**（注意：项目**没有实现真正的"秒传"**，即按 hash 直接命中已有文件跳过上传）。
每片校验会话归属（403）、下标范围、重复片（409）、MD5（400）后才落盘。

> **已知限制**：会话存在**进程内模块级字典**里，重启即丢、多 worker 不共享。生产化需挪到 Redis。

### ⑫ 通知：为什么用进程内广播而不是 Redis

`notification_bus` 存在的理由是**分层**：通知要在点赞/评论/关注里发出，但不该让 service
去 import router（会倒置依赖并循环 import）。所以中间放一个进程内的发布/订阅。

投递是**尽力而为**：`put_nowait`，队列满就丢弃 —— 因为客户端重新加载时会从 MySQL
重拉，丢一条推送不等于丢数据。

> **已知限制**：进程内队列意味着多 worker 下发布只到同 worker 的连接。当前 Docker
> 单 worker 所以成立；换 Redis Pub/Sub 时只需替换 `subscribe/publish/unsubscribe` 三个函数。

---

# 接口一览

全部为 `POST`（除标注外），请求/响应体为 JSON。带锁标记的需要 `Authorization: Bearer <access_token>`。

## 账号 `/account`（11）

| 接口 | 说明 | 需登录 |
|---|---|---|
| `/register` | 注册（限流 5 次/小时/IP） | |
| `/login` | 登录（限流 10 次/分钟/IP） | |
| `/refresh` | 用 access + refresh 换新令牌 | |
| `/changePassword` | 改密（改完 refresh 失效） | |
| `/findByID` | 按 ID 查用户 | |
| `/findByUsername` | 按用户名查用户 | |
| `/getProfile` | 个人资料 | |
| `/logout` | 登出 | ✓ |
| `/rename` | 改名 | ✓ |
| `/uploadAvatar` | 上传头像（multipart） | ✓ |
| `/updateProfile` | 更新简介等 | ✓ |

## 视频 `/video`（9）

| 接口 | 说明 | 需登录 |
|---|---|---|
| `/listByAuthorID` | 某作者的作品列表 | |
| `/getDetail` | 视频详情（三层缓存） | |
| `/publish` | 发布（写 `outbox_msgs` 同事务） | ✓ |
| `/uploadVideo` | 整文件上传（≤200MB，一次性读入内存） | ✓ |
| `/uploadCover` | 上传封面 | ✓ |
| `/chunk/init` | 分片上传：初始化/续传 | ✓ |
| `/chunk/upload` | 上传单片 | ✓ |
| `/chunk/status` | 查询已传分片 | ✓ |
| `/chunk/complete` | 合并分片 | ✓ |

## 点赞 `/like`（4，限流 30 次/分钟）

`/like` · `/unlike` · `/isLiked` · `/listMyLikedVideos` —— 全部需登录。

## 评论 `/comment`（3，写限流 10 次/分钟）

| 接口 | 说明 | 需登录 |
|---|---|---|
| `/listAll` | 某视频的评论列表 | |
| `/publish` | 发评论 | ✓ |
| `/delete` | 删评论 | ✓ |

## 关注 `/social`（5，限流 20 次/分钟）

`/follow` · `/unfollow` · `/getAllFollowers` · `/getAllVloggers` · `/getCounts` —— 全部需登录。

## Feed `/feed`（6）

| 接口 | 说明 | 需登录 |
|---|---|---|
| `/listLatest` | 最新（热冷分离 + 毫秒游标） | 可选 |
| `/listLikesCount` | 最多赞（`(likes_count, id)` 游标） | 可选 |
| `/listByPopularity` | 热门（三列复合游标） | 可选 |
| `/listByTag` | 按标签 | 可选 |
| `/search` | 搜索视频 | 可选 |
| `/listByFollowing` | 关注的时间线 | ✓ |

> "需登录：可选"指用 `get_optional_user` —— 未登录也能浏览，登录后响应里会多出
> `isLiked` / `isFollowed` 这类个性化字段。

## 私信 `/message`（2，需登录）

`/send` · `/list`

## 通知 `/notification`（4）

| 接口 | 说明 | 需登录 |
|---|---|---|
| `GET /stream` | **SSE** 实时推送（30s keepalive） | 走 stateless 认证 |
| `/list` | 通知列表 | ✓ |
| `/markRead` | 标记已读 | ✓ |
| `/unreadCount` | 未读数 | ✓ |

## AI 助手 `/agent`（6，需登录）

| 接口 | 说明 |
|---|---|
| `/conversations` | 新建会话 |
| `/conversations/list` | 会话侧栏列表 |
| `/conversations/delete` | 删除会话 |
| `/conversations/history` | 拉历史消息 |
| `/chat` | **SSE** 发起一轮对话（写操作会在此挂起等确认） |
| `/confirm` | **SSE** 提交"同意 / 拒绝"并恢复图 |

> 未配置 `OPENAI_API_KEY` 时，这 6 个接口全部返回 **503**。

## 其他

`GET /healthz` —— 健康检查，返回 `{"status": "ok"}`。
`GET /docs` —— Swagger UI（FastAPI 自动生成）。

---

# 已知缺口

写文档时把限制写清楚，比让人踩一遍强：

- **限流在 Redis 不可用时完全失效**（见「后端亮点 ①」，实测 20 并发 0 拦截）；
- **热门榜的 Redis 分钟窗口快照（`hot:video:1m:*` + `ZUNIONSTORE`）只有读路径、没有写入方**，
  所以实际每次都回退到 MySQL 三重游标 —— 设计在，链路是死的；
- **`outbox_msgs` 只落地了存储半边**（发布视频时同事务写入），中继消费者未实现；
- **分片上传会话存进程内存**，且没有真正的秒传；
- **通知实时推送用进程内队列**，多 worker 下只有同 worker 能收到；
- 整文件上传 `/video/uploadVideo` 是 `await file.read()` **一次性读进内存**（限 200MB）；
- `/account/getProfile` 的视频数/获赞数统计是**硬编码 0**；
- **没有数据库迁移工具**：建表全靠 SQLAlchemy `create_all`，它只建不改 —— 已有表的结构
  变更不会被应用，Model 字段改了需要手动 `ALTER` 或重建表。生产环境应换成 Alembic。
