"""
数据库引擎 + 会话工厂 + ORM 基类——整个项目的 MySQL 入口。

技术选型：
  - SQLAlchemy 2.0 异步：原生支持 async/await，配合 FastAPI 不阻塞事件循环
  - asyncmy 驱动：纯 Python 实现，不需要 MySQL C 客户端，pip install 完就能用
  - async_sessionmaker：每个 HTTP 请求创建一个独立会话，请求结束自动回收

数据流：
  HTTP 请求进来 → Depends(get_db) → 创建 AsyncSession → 注入 Router
  → Router → Service → Repo → Repo 用 self.db 执行 SQL
  → 请求成功 → get_db() 自动 commit → 会话关闭
  → 请求异常 → get_db() 自动 rollback → 会话关闭
"""
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

# 构建连接字符串——和 Go 项目的 DSN 格式一致
# charset=utf8mb4 必须用 utf8mb4，否则 emoji 存不了（utf8 只支持 3 字节，emoji 是 4 字节）
DATABASE_URL = (
    f"mysql+asyncmy://{settings.mysql_user}:{settings.mysql_password}"
    f"@{settings.mysql_host}:{settings.mysql_port}/{settings.mysql_database}"
    f"?charset=utf8mb4"
)

# 创建异步引擎
# echo=False：不打印 SQL 日志（开发调试时可临时改成 True）
# pool_size=10：连接池最多保持 10 个空闲连接
# max_overflow=20：连接池满了之后最多再创建 20 个临时连接（总共 30 个并发连接）
engine = create_async_engine(DATABASE_URL, echo=False, pool_size=10, max_overflow=20)

# 会话工厂——不是会话本身，是"创建会话的工厂"
# expire_on_commit=False：commit 后不使对象过期，这样 commit 后还能访问对象的属性
# class_=AsyncSession：指定工厂生产的是异步会话
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    """
    所有 ORM Model 的基类。

    任何想映射到数据库表的类，必须继承 Base。
    这样 SQLAlchemy 才能发现它、管理它。

    用法：
      class Account(Base):
          __tablename__ = "accounts"
          id: Mapped[int] = mapped_column(primary_key=True)
          ...
    """
    pass


async def get_db():
    """
    FastAPI 依赖注入——每个请求一个独立会话。

    用法：在 Router 函数参数里写 db: AsyncSession = Depends(get_db)

    为什么 per-request？
      - 会话不是线程安全的，多个请求共享一个会话会导致数据混乱
      - 每个请求独立 commit/rollback，互不干扰
      - 请求结束自动归还连接到连接池

    yield 的含义：
      - yield 之前的代码在"请求开始"时执行
      - yield 本身是"会话"对象，注入给 Router
      - yield 之后的代码在"请求结束"时执行（自动 commit/rollback）

    所以 Router 不需要手动 commit——get_db 帮你做了。
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session          # 注入给 Router
            await session.commit() # 请求成功 → commit
        except Exception:
            await session.rollback()  # 请求异常 → rollback
            raise                     # 继续向上抛异常，让 Router 的异常处理器处理
        # async with 退出时自动调 session.close()，归还连接到连接池
