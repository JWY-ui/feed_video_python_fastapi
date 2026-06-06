"""
FastAPI 应用入口——整个项目的启动点。

启动命令：
  uvicorn app.main:app --reload --port 8080

启动时做了什么（lifespan 函数）：
  1. 连 MySQL（不指定数据库）→ CREATE DATABASE IF NOT EXISTS
  2. 连指定数据库 → Base.metadata.create_all() 建所有表
  3. 连 Redis（可选，失败不阻塞）

关闭时做了什么：
  1. 关 Redis 连接
  2. 关 MySQL 连接池

路由注册：app.include_router() 把所有模块的路由挂到对应前缀下。
限流配置：在 include_router 时注入 rate_limit Depends。
静态文件：app.mount("/static", ...) 让上传的视频/头像可直接通过 URL 访问。
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.database import engine, Base
from app.utils.redis_client import redis_client

# ━━ 导入所有 Model —— 让 Base.metadata 知道有哪些表 ━━
# 即使这些 import 看起来"没用"，但 import 时 SQLAlchemy 会执行 __init_subclass__，
# 把每个 Model 注册到 Base.metadata 中。create_all() 需要这个注册表。
from app.models import (
    Account, Video, OutboxMsg, Like, Comment,
    Social, Tag, VideoTag, Message, Notification,
)  # noqa: F401

# ━━ 导入所有路由 ━━
from app.routers.account import public_router as account_public_router
from app.routers.account import protected_router as account_protected_router
from app.routers.video import public_router as video_public_router
from app.routers.video import protected_router as video_protected_router
from app.routers.like import router as like_router
from app.routers.comment import public_router as comment_public_router
from app.routers.comment import protected_router as comment_protected_router
from app.routers.social import router as social_router
from app.routers.feed import public_router as feed_public_router
from app.routers.feed import protected_router as feed_protected_router
from app.routers.message import router as message_router
from app.routers.notification import router as notification_router

# ━━ 限流配置 ━━
from app.middleware.rate_limit import rate_limit

# 登录：每个 IP 每分钟最多 10 次（防暴力破解）
login_limiter = rate_limit("account_login", 10, 60)
# 注册：每个 IP 每小时最多 5 次（防批量注册）
register_limiter = rate_limit("account_register", 5, 3600)
# 点赞：每个账号每分钟最多 30 次
like_limiter = rate_limit("like_write", 30, 60)
# 评论：每个账号每分钟最多 10 次
comment_limiter = rate_limit("comment_write", 10, 60)
# 关注：每个账号每分钟最多 20 次
social_limiter = rate_limit("social_write", 20, 60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    应用生命周期管理——FastAPI 启动和关闭时自动执行。

    @asynccontextmanager 把一个 async 函数变成上下文管理器。
    yield 之前的代码在"启动时"执行，yield 之后的代码在"关闭时"执行。
    """
    from app.config import settings
    import asyncmy

    # ━━ 启动：创建数据库（如果不存在）━━━
    # 注意：这里连接时不指定数据库名，因为数据库可能还不存在
    try:
        conn = await asyncmy.connect(
            host=settings.mysql_host, port=settings.mysql_port,
            user=settings.mysql_user, password=settings.mysql_password,
        )
        await conn.execute(
            f"CREATE DATABASE IF NOT EXISTS `{settings.mysql_database}` "
            f"DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
        )
        await conn.ensure_closed()
    except Exception:
        pass  # 连不上 MySQL——后面建表步骤会真正报错

    # ━━ 启动：自动建表 ━━
    # Base.metadata.create_all() 检查每张表是否存在，不存在则 CREATE TABLE
    # 注意：只建表不修改表——如果改过 Model 字段，需要手动 ALTER 或删库重建
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # ━━ 启动：连接 Redis（可选，失败不阻塞）━━━
    await redis_client.connect()
    if redis_client.available:
        print("✅ Redis 已连接")
    else:
        print("⚠️ Redis 未连接，降级运行")

    yield  # ← 应用运行中——请求在这条线之后才开始处理

    # ━━ 关闭：清理资源 ━━
    await redis_client.close()
    await engine.dispose()


# FastAPI 实例——这是 uvicorn 要找的 app 对象
app = FastAPI(
    title="Feed 流视频系统",
    description="短视频 Feed 流 API",
    version="1.0.0",
    lifespan=lifespan,
)

# ━━ CORS 跨域配置 ━━
# 前端可能在 localhost:5173，后端在 localhost:8080——不同端口算"跨域"
# 不加 CORS 中间件，浏览器会拦截所有跨域请求
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],       # 生产环境应限制为具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ━━ 静态文件服务 ━━
# 上传的视频/头像/封面都存在 uploads/ 目录下
# mount 后可通过 http://localhost:8080/static/videos/1/20240601/abc.mp4 直接访问
app.mount("/static", StaticFiles(directory="uploads"), name="static")

# ━━ 注册全部路由（44 个接口）━━━
# 每个 include_router 把一个模块的接口挂到指定 URL 前缀下
# tags 参数让 Swagger 文档按模块分组显示

# Account：12 个接口（注册/登录/查询/改名/改密/登出/头像/简介）
app.include_router(account_public_router, prefix="/account", tags=["1. 用户"])
app.include_router(account_protected_router, prefix="/account", tags=["1. 用户"])

# Video：9 个接口（上传/发布/分片/详情）
app.include_router(video_public_router, prefix="/video", tags=["2. 视频"])
app.include_router(video_protected_router, prefix="/video", tags=["2. 视频"])

# Like：4 个接口 + 限流
app.include_router(like_router, prefix="/like", tags=["3. 点赞"],
                   dependencies=[Depends(like_limiter)])

# Comment：3 个接口（listAll 公开，publish/delete 需登录 + 限流）
app.include_router(comment_public_router, prefix="/comment", tags=["4. 评论"])
app.include_router(comment_protected_router, prefix="/comment", tags=["4. 评论"],
                   dependencies=[Depends(comment_limiter)])

# Social：5 个接口 + 限流
app.include_router(social_router, prefix="/social", tags=["5. 关注"],
                   dependencies=[Depends(social_limiter)])

# Feed：5 种 Feed 流（软鉴权，没登录也能浏览）
app.include_router(feed_public_router, prefix="/feed", tags=["6. Feed 流"])
app.include_router(feed_protected_router, prefix="/feed", tags=["6. Feed 流"])

# Message：2 个接口（发送/列表）
app.include_router(message_router, prefix="/message", tags=["7. 私信"])

# Notification：4 个接口（SSE 实时推送/列表/已读/计数）
app.include_router(notification_router, prefix="/notification", tags=["8. 通知"])


@app.get("/healthz")
async def healthz():
    """
    健康检查接口——负载均衡器 / K8s liveness probe 用。

    返回 {"status": "ok"} 表示服务还活着、能处理 HTTP 请求。
    如果数据库连不上这里不会报错——需要更全面的健康检查可加 DB ping。
    """
    return {"status": "ok"}
