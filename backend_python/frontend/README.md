# 前端 · 短视频社区

Vue 3 + TypeScript 单页应用，对接上一级的 **Python / FastAPI 后端**（`../`）。
开发时通过 Vite 代理把 `/api/...` 转发到 `http://127.0.0.1:8080/...`。

## 技术栈

Vue 3.5（`<script setup>`）· TypeScript 5.9 · Vue Router 4 · Pinia 3 ·
Vite（rolldown-vite 7）· `spark-md5`（分片上传校验）

## 页面

| 路由 | 页面 | 说明 |
|---|---|---|
| `/` | 推荐页 | 网红卡片流，推荐 / 关注 / 点赞榜三个 Tab，客户端搜索过滤，滚动加载更多 |
| `/hot` | 热榜 | 对接 `/feed/listByPopularity` |
| `/video` | 发布页 | 登录后可发布；**5MB 分片上传**（最多 3 片并发、每片重试 3 次、断点续传） |
| `/video/:id` | 视频详情 | 播放、点赞、评论抽屉、作者信息 |
| `/account` | 账号页 | 登录、个人信息、粉丝/关注入口 |
| `/account/register` | 注册页 | |
| `/account/change-password` | 改密页 | |
| `/settings` | 设置页 | 改名、退出登录 |
| `/u/:id` | 用户主页 | 作品、粉丝/关注列表、关注/取关、私信入口 |
| `/messages` | 私信联系人 | 从粉丝与关注里挑人开聊 |
| `/messages/:peerId` | 私信会话 | 最近 50 条往来，自己的消息靠右 |
| `/notifications` | 通知页 | 点赞/评论/关注/@提及，SSE 实时 +1 红点 |

未登录访问 `meta.requiresAuth` 的路由会跳到 `/account?redirect=<原路径>`。

## 关键实现

**API 客户端（`src/api/client.ts`）** —— 401 时自动刷新并重试原请求。
刷新是**单飞**的（并发请求只触发一次），结果做成三态：`refreshed` 重试、
`invalid` 清会话、`transient` **不清会话**（否则一次网络抖动就把用户登出）。
登录/注册/改密被排除在自动重试之外。

**SSE 客户端（`src/api/sseStream.ts`）** —— 用 `fetch` + `ReadableStream` 手写，
不用 `EventSource`，因为通知与助手的流都用 `Authorization` 头认证，而 `EventSource`
发不了自定义头。内含跨 chunk 的帧边界处理、指数退避重连、401 复用上面的单飞刷新。
通知流与助手流共用这一个模块；助手的流是 POST 且**关闭自动重连**（重连会重发整轮请求）。

**悬浮 AI 助手（`src/components/AgentPanel.vue`）** —— 挂在 `App.vue`、位于
`<RouterView>` **之外**，所以助手操作页面跳转时对话本身不会被卸载。
它消费后端工具返回的 `ui` 指令（白名单：`navigate` / `toast`），
路径经 `src/utils/uiActions.ts` 二次校验（只接受 `/` 开头且非 `//`，防开放重定向），
同一轮内多个跳转只取最后一个。详见根目录 `README.md` 第一部分。

**分片上传（`src/views/VideoView.vue`）** —— `spark-md5` 流式计算整文件 MD5 与每片 MD5；
按文件 MD5 复用上传会话，刷新页面后可续传。

**时间显示（`src/utils/time.ts`）** —— 后端返回的时间串不带时区偏移，
必须先补 `Z` 再解析，否则在 UTC+8 机器上整体偏 8 小时。

## 开发

先启动后端（在 `../` 目录，即 `backend_python/`）：

```bash
cd ..
"/d/miniconda3/envs/langchain/python.exe" -m uvicorn app.main:app --reload --port 8080
```

再启动前端：

```bash
npm install
npm run dev          # http://localhost:5173
```

代理目标可在 `vite.config.ts` 调整；接口根路径可用环境变量 `VITE_API_BASE` 覆盖
（默认 `/api`）。

## 构建

```bash
npm run build        # 先跑 vue-tsc 类型检查，再 vite build
```

Docker Compose 部署时前端由 Nginx 托管构建产物，并把 `/api` 反向代理到后端，
同时对 SSE 关闭了 `proxy_buffering`（否则流会被攒批，实时推送失效）。
