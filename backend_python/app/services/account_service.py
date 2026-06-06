"""
Account 业务逻辑层（Service）

只处理 dict 和基本类型，不 import 任何 SQLAlchemy Model。
"""
from sqlalchemy.exc import IntegrityError

from app.repositories.account_repo import AccountRepository
from app.schemas.account import UpdateProfileRequest
from app.utils import password as pwd
from app.utils import jwt_helper


class AccountService:

    def __init__(self, repo: AccountRepository):
        self.repo = repo

    # ━━━ 注册 ━━━
    async def register(self, username: str, password: str) -> None:
        hashed = pwd.hash_password(password)
        await self.repo.create(username, hashed)

    # ━━━ 登录 ━━━
    async def login(self, username: str, password: str) -> tuple[str, str, dict]:
        """
        登录成功返回 (access_token, refresh_token, user_dict)
        user_dict = {"id", "username", "avatar_url", "bio"} 可直接转 Schema
        """
        user = await self.repo.find_by_username(username)
        if user is None:
            raise ValueError("user not found")

        if not pwd.verify_password(password, user["password"]):
            raise ValueError("invalid password")

        access_token = jwt_helper.create_access_token(user["id"], user["username"])
        refresh_token = jwt_helper.create_refresh_token()

        await self.repo.update_token(user["id"], access_token, refresh_token)
        return access_token, refresh_token, {
            "id": user["id"], "username": user["username"],
            "avatar_url": user["avatar_url"], "bio": user["bio"],
        }

    # ━━━ 刷新 Token ━━━
    async def refresh_access_token(self, refresh_token: str, access_token: str) -> tuple[str, int, str]:
        """
        刷新 Access Token——用过期 Token 拿 user_id，O(1) 查用户。

        为什么传两个 Token？
          refresh_token 是随机字符串，不含任何用户信息，无法知道属谁。
          过期 access_token 虽然过期了但 payload 里的 account_id 还在。
          解码时跳过过期验证，拿出 account_id，再查这个用户的 refresh_token 是否匹配。

        从 O(N) 全表扫描优化为 O(1) 主键查询。
        """
        if not refresh_token:
            raise ValueError("refresh token is empty")

        # 1. 从过期 access_token 解码出 account_id（跳过 exp 验证）
        try:
            payload = jwt_helper.decode_token_skip_expiry(access_token)
        except jwt_helper.JWTError:
            raise ValueError("invalid access token")

        # 2. O(1) 查用户
        u = await self.repo.find_by_id(payload["account_id"])
        if u is None or u["refresh_token"] != refresh_token:
            raise ValueError("invalid refresh token")

        # 3. 生成新 token
        new_token = jwt_helper.create_access_token(u["id"], u["username"])
        await self.repo.update_token(u["id"], new_token, u["refresh_token"])
        return new_token, u["id"], u["username"]

    # ━━━ 登出 ━━━
    async def logout(self, account_id: int) -> None:
        user = await self.repo.find_by_id(account_id)
        if user is None:
            raise ValueError("account not found")
        if user["token"] == "":
            return
        await self.repo.clear_token(account_id)

    # ━━━ 改密 ━━━
    async def change_password(self, username: str, old_password: str, new_password: str) -> None:
        user = await self.repo.find_by_username(username)
        if user is None:
            raise ValueError("user not found")

        if not pwd.verify_password(old_password, user["password"]):
            raise ValueError("invalid old password")

        new_hash = pwd.hash_password(new_password)
        await self.repo.update_password(user["id"], new_hash)
        await self.repo.clear_token(user["id"])

    # ━━━ 查询 ━━━
    async def find_by_id(self, account_id: int) -> dict:
        user = await self.repo.find_by_id(account_id)
        if user is None:
            raise ValueError("account not found")
        return user

    async def find_by_username(self, username: str) -> dict:
        user = await self.repo.find_by_username(username)
        if user is None:
            raise ValueError("account not found")
        return user

    # ━━━ 改名 ━━━
    async def rename(self, account_id: int, new_username: str) -> str:
        if not new_username or not new_username.strip():
            raise ValueError("new_username is required")

        new_token = jwt_helper.create_access_token(account_id, new_username.strip())

        try:
            await self.repo.rename(account_id, new_username.strip(), new_token)
        except IntegrityError:
            raise ValueError("username already exists")

        return new_token

    # ━━━ 头像与简介 ━━━
    async def update_avatar(self, account_id: int, avatar_url: str) -> None:
        await self.repo.update_avatar(account_id, avatar_url)

    async def update_profile(self, account_id: int, req: UpdateProfileRequest) -> None:
        updates = {}
        if req.bio is not None and req.bio.strip():
            updates["bio"] = req.bio.strip()
        if req.avatar_url is not None and req.avatar_url.strip():
            updates["avatar_url"] = req.avatar_url.strip()
        if not updates:
            raise ValueError("nothing to update")
        await self.repo.update_fields(account_id, **updates)
