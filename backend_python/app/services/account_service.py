# -*- coding: utf-8 -*-
"""
Account business logic layer (Service).

Operates only on dicts and primitives, never imports SQLAlchemy Models.
"""
from sqlalchemy.exc import IntegrityError

from app.repositories.account_repo import AccountRepository
from app.schemas.account import UpdateProfileRequest
from app.utils import password as pwd
from app.utils import jwt_helper


class AccountService:

    def __init__(self, repo: AccountRepository):
        self.repo = repo

    # ---- Register ----
    async def register(self, username: str, password: str) -> None:
        hashed = pwd.hash_password(password)
        await self.repo.create(username, hashed)

    # ---- Login ----
    async def login(self, username: str, password: str) -> tuple[str, str, dict]:
        """
        Login success returns (access_token, refresh_token, user_dict).
        user_dict = {"id", "username", "avatar_url", "bio"} can be directly converted to Schema.
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

    # ---- Refresh Token ----
    async def refresh_access_token(self, refresh_token: str, access_token: str) -> tuple[str, int, str]:
        """
        Refresh Access Token -- use expired token to get user_id, O(1) user lookup.

        Why send two tokens?
          refresh_token is a random string, contains no user info, can't identify owner.
          Expired access_token has expired but its payload still contains account_id.
          Decode skipping expiry check, extract account_id, then verify refresh_token matches.

        Optimized from O(N) full table scan to O(1) PK lookup.
        """
        if not refresh_token:
            raise ValueError("refresh token is empty")

        # 1. Extract account_id from expired access_token (skip exp validation)
        try:
            payload = jwt_helper.decode_token_skip_expiry(access_token)
        except jwt_helper.JWTError:
            raise ValueError("invalid access token")

        # 2. O(1) user lookup by PK
        u = await self.repo.find_by_id(payload["account_id"])
        if u is None or u["refresh_token"] != refresh_token:
            raise ValueError("invalid refresh token")

        # 3. Generate new token
        new_token = jwt_helper.create_access_token(u["id"], u["username"])
        await self.repo.update_token(u["id"], new_token, u["refresh_token"])
        return new_token, u["id"], u["username"]

    # ---- Logout ----
    async def logout(self, account_id: int) -> None:
        user = await self.repo.find_by_id(account_id)
        if user is None:
            raise ValueError("account not found")
        if user["token"] == "":
            return
        await self.repo.clear_token(account_id)

    # ---- Change Password ----
    async def change_password(self, username: str, old_password: str, new_password: str) -> None:
        user = await self.repo.find_by_username(username)
        if user is None:
            raise ValueError("user not found")

        if not pwd.verify_password(old_password, user["password"]):
            raise ValueError("invalid old password")

        new_hash = pwd.hash_password(new_password)
        await self.repo.update_password(user["id"], new_hash)
        await self.repo.clear_token(user["id"])

    # ---- Query ----
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

    # ---- Rename ----
    async def rename(self, account_id: int, new_username: str) -> str:
        if not new_username or not new_username.strip():
            raise ValueError("new_username is required")

        new_token = jwt_helper.create_access_token(account_id, new_username.strip())

        try:
            await self.repo.rename(account_id, new_username.strip(), new_token)
        except IntegrityError:
            raise ValueError("username already exists")

        return new_token

    # ---- Avatar & Bio ----
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
