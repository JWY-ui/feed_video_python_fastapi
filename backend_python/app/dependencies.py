"""
公用依赖注入——Account 模块的 Repo → Service 依赖链。

FastAPI Depends 如何递归解析：

  Router 里写：
    async def register(service: AccountService = Depends(get_account_service))

  FastAPI 看到 Depends(get_account_service)，自动：
    1. 调 get_account_service()
    2. 发现它也需要 Depends(get_account_repo)
    3. 调 get_account_repo()
    4. 发现它也需要 Depends(get_db)
    5. 调 get_db() → 创建 AsyncSession → 传给 get_account_repo
    6. get_account_repo(session) → 返回 AccountRepository → 传给 get_account_service
    7. get_account_service(repo) → 返回 AccountService → 注入到 Router 函数

  → Router 函数的 service 参数就是完整的 AccountService 实例

为什么要用 Depends 而不是在 main.py 里手动 new？
  - 每个请求一条独立依赖链（线程安全）
  - 单元测试时可以替换 Depends（注入 Mock 对象）
  - 不需要在 main.py 维护依赖组装顺序

其他模块（Video、Like、Comment 等）的依赖链在自己的 Router 文件里内联定义，
因为它们不需要跨模块共享。
"""
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.repositories.account_repo import AccountRepository
from app.services.account_service import AccountService


def get_account_repo(db: AsyncSession = Depends(get_db)) -> AccountRepository:
    """
    创建 AccountRepository 实例。

    每个请求调一次 → 每个请求一个独立 Repo 实例 → 绑定当前请求的会话。
    """
    return AccountRepository(db)


def get_account_service(repo: AccountRepository = Depends(get_account_repo)) -> AccountService:
    """
    创建 AccountService 实例。

    依赖链：get_db → get_account_repo → get_account_service
    FastAPI 自动递归解析，不需要手动组装。
    """
    return AccountService(repo)
