# 短视频平台 · Python 后端 + 站内 AI 助手

一个完整的短视频社区服务端：Feed、点赞、评论、关注、私信、通知、标签、分片上传，
外加一个**能替你操作站内功能、但写操作必须经你确认**的 AI 助手。

> **规模**：后端 Python 约 6600 行（其中助手 1760 行，业务后端 4879 行）
> + 前端 TypeScript/Vue 约 5100 行；**44 个业务接口 + 6 个助手接口**；
> 20 个 AI 工具；**95 项自动化测试**。

## 目录

- [第一部分 · 站内 AI 助手](#第一部分--站内-ai-助手)
- [第二部分 · 短视频平台后端](#第二部分--短视频平台后端)
- [附 · 面试与简历](#附--面试与简历) —— 面试开场介绍 / 可直接摘用的要点 / 常见追问答法

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

## 已知缺口（如实列出）

写文档时把限制写清楚，比让人踩一遍强：

- **限流在 Redis 不可用时完全失效**（见 ①，实测 20 并发 0 拦截）；
- **热门榜的 Redis 分钟窗口快照（`hot:video:1m:*` + `ZUNIONSTORE`）只有读路径、没有写入方**，
  所以实际每次都回退到 MySQL 三重游标 —— 设计在，链路是死的；
- **`outbox_msgs` 只落地了存储半边**（发布视频时同事务写入），中继消费者未实现；
- **分片上传会话存进程内存**，且没有真正的秒传；
- **通知实时推送用进程内队列**，多 worker 下只有同 worker 能收到；
- 整文件上传 `/video/uploadVideo` 是 `await file.read()` **一次性读进内存**（限 200MB）；
- `/account/getProfile` 的视频数/获赞数统计是**硬编码 0**；
- 仓库里曾有 112 个 `.pyc` 被 git 跟踪（现已加 `.gitignore`，但仍需 `git rm --cached` 摘除）。

---

# 附 · 面试与简历

## 面试开场介绍

### 电梯版（约 15 秒，被问"讲讲你这个项目"时先用它开口）

> 一个短视频社区的全栈项目：Python FastAPI 后端 44 个接口、Vue 3 前端。
> 我最近在上面做的是**站内 AI 助手** —— 能替用户找视频、发私信，
> 但**对外可见的写操作必须先弹确认卡**，用户点了才真的发出去。

### 主用版（约 2 分钟）

> 这个项目是一个短视频社区，后端 Python + FastAPI、前端 Vue 3，
> 44 个业务接口，跑在 MySQL 和 Redis 上。
>
> 我做得最深的是**站内 AI 助手**这一块 —— 一个悬浮在页面右下角的助手。
> 用户可以让它找视频、看评论，也可以让它**替自己发私信、发评论**。
> 这里最核心的约束是一条产品规则：**读操作直接执行，但对外可见的写操作必须先弹确认卡**。
>
> 我用 LangGraph 实现，靠它的 `interrupt()` 和 `Command(resume=)`，把
> "挂起 → 等用户拍板 → 恢复"做成了一个**可持久化的状态机**。
> 状态存在 MySQL 里，所以用户关掉页面再回来、或者"点确认"的那个请求和
> "发起对话"的请求不是同一个连接，图都能接着往下走。
>
> 我在上面花时间最多的其实不是功能，是两件事：**验证**和**并发**。
>
> 验证上：`interrupt`/`resume` 的语义是最容易写错、也最容易被后续改动**静默打破**的
> 地方，但它依赖大模型，很难稳定复现。我的做法是把模型换成一个桩，
> 但驱动的是**真实的图加真实的 MySQL checkpointer**，这样就能确定性地断言
> "写操作挂起时不执行、批准后才执行、拒绝后不执行并且要告知模型"。
>
> 并发上：我压测时发现，同一个会话上两个"确认"同时到达，**写操作会执行两遍** ——
> 也就是同一条私信会发出去两条。根因是同一个会话上没有任何串行化，
> 两个图运行同时读写同一份 checkpoint。后来用**按会话加锁 + 确认接口幂等**修掉了，
> 实测从 2 次降到 1 次；同根因还藏着两个更隐蔽的问题也一并修了。
>
> 另外还有一个我印象很深的 bug：第三方 checkpointer 库的 SQL 里有个派生列没写
> `COLLATE`，跟项目数据库的排序规则冲突，**用户发的第一条消息就会失败**。
> 这个用内存 checkpointer 测根本测不出来，只有接真实数据库才会暴露。

### 对方想深入时，按这个顺序展开（挑他感兴趣的那条）

1. **为什么用 LangGraph 而不是自己写 ReAct 循环** —— 关键是 `interrupt()` + checkpointer：手写要维护一个可中断、可序列化、能在另一个 HTTP 请求里恢复的状态机。
2. **三级工具权限怎么划分** —— 按"能否撤销 + 影响面"：点赞/关注有反向操作；发私信/发评论对外可见且撤不回。
3. **那个 `COLLATE` bug 的完整定位过程** —— 从"桩模型全绿但接真库就炸"到在库源码里找到 `json_table` 派生列。
4. **并发问题的压测方法** —— 30 路并发 + 真 socket 断开，以及为什么单测覆盖不到。
5. **后端的设计** —— Feed 热冷分离、Lua 滑动窗口限流、双令牌刷新。
6. **前端为什么把助手做成悬浮面板** —— 挂在 `RouterView` 之外，跳转时对话才不会被卸载。

> **讲述提醒**：这几条都能追到具体代码和实测数字。如果对方要求"看代码"，
> 直接翻 `backend_python/app/agent_v3/` —— 模块划分和注释都是按"别人能读懂"写的。

## 可直接摘用的要点

**AI 助手部分**

- 基于 **LangGraph** 实现带 human-in-the-loop 的站内助手：用动态 `interrupt()` /
  `Command(resume=)` 把"读操作直接执行、**对外可见的写操作必须用户确认**"做成可持久化、
  可跨请求恢复的状态机；用桩模型（不依赖真模型与网络）驱动真实图与 MySQL checkpointer
  写成回归测试。
- 定位并修复**并发下的重复写操作**：同一会话两个"确认"并发到达时写操作执行两次
  （私信发出两条）。通过按会话串行化 + 确认接口幂等修复，压测验证 2 次 → 1 次；
  同根因的"并发轮次丢消息""确认卡开着时新消息销毁待确认操作"一并修复。
- 诊断出一个**仅真实 checkpointer 才暴露的线上级故障**：三方库 SQL 中 `json_table`
  派生列未指定 `COLLATE`，与项目库排序规则冲突导致首次对话即失败；在启动时幂等对齐
  checkpoint 表解决。
- 设计**三级工具权限模型**（read / 可逆写 / 公开写）与 20 个工具；身份由服务端注入
  （模型无法伪造），UI 指令由服务端构造 + 前端白名单二次校验。

**后端部分**

- 设计并实现短视频社区后端：**FastAPI + SQLAlchemy 2.0 async + MySQL + Redis**，
  严格 router / service / repository 分层（repository 是唯一接触 ORM 的地方、只返回 dict），
  44 个接口。
- 用 **Lua 脚本在 Redis 里实现 ZSET 滑动窗口限流**，一次解决 `INCR + EXPIRE` 竞态
  与固定窗口边界 2× 突发两个问题。
- 设计 **access + refresh 双令牌**：access 为 15 分钟无状态 JWT，refresh 为可吊销的
  随机串存库；刷新时"**验签但跳过 exp**"取出 account_id 再按主键比对，把全表扫描
  优化成 O(1) 查询。
- 为视频详情设计**三层缓存防护**：随机 TTL 防雪崩、`SETNX` 互斥锁防击穿、
  空值哨兵防穿透。
- 实现 **Feed 热冷分离**：以 Redis ZSET 最旧 score 作 watermark 决定走内存还是 MySQL，
  热区不足自动拼冷数据；ZSET 重建用 `asyncio.Lock` 单飞防惊群。
- 列表分页全部使用**复合游标**（如 `(likes_count, id)`）而非 OFFSET，
  并以 id 作 tiebreaker 避免翻页边界重复/漏项。
- 排查并修复**时间线整体偏 8 小时且翻页重复**的时区问题，收口为统一的 naive-UTC
  读写约定。
- 把 Redis 设计为**可选依赖**：连接失败不抛异常，每个方法返回语义化的安全默认值，
  业务层零 `if` 分支；本地开发不起 Redis 也能跑通全链路。

## 可能被追问的点（想清楚再写）

| 追问 | 怎么答 |
|---|---|
| 为什么用 LangGraph 而不是自己写 ReAct 循环？ | 核心是 `interrupt()`/checkpointer：手写要维护一个可中断、可序列化、能在**另一个 HTTP 请求里**恢复的状态机，这正是 checkpointer 做完的事 |
| 为什么要确认机制？模型直接发私信不行吗？ | 安全与产品两条理由：写操作不可撤回，且"LLM 自主发私信"不可接受；确认机制天然是一个检查点 |
| 工具权限分三级怎么定的？ | 按"能否撤销 + 影响面"：点赞/关注有反向操作；发私信/发评论对外可见且撤不回 |
| 并发问题为什么之前没发现？ | 单测覆盖不到：需要同一个会话上两个请求真并发。是压测（30 路并发 + 真 socket 断开）才暴露的 |
| 怎么证明修好了？ | 先写失败的测试（修复前实测执行 2 次），再修，测试转绿并留在回归套件里 |
| 分页为什么不用 OFFSET？ | 深分页要扫描并丢弃前 N 行；且翻页期间有新增/删除会导致重复或漏项。复合游标 + id tiebreaker 两者都解决 |
| 为什么 refresh token 不做成 JWT？ | JWT 无法吊销。做成随机串存库后，登出/改密即可立即失效；代价是刷新要查一次库，所以用"验签跳过 exp"把这次查询压成主键查询 |
| 限流为什么要用 Lua？ | "清理→计数→判断→记录"四步必须原子，否则两个并发请求会各自读到旧计数、双双放行 |
