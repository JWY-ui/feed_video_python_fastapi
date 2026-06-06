# -*- coding: utf-8 -*-
"""
Follow business logic -- entire chain operates on primitives and dicts.
"""
from app.repositories.social_repo import SocialRepository
from app.repositories.account_repo import AccountRepository


class SocialService:

    def __init__(self, repo: SocialRepository, account_repo: AccountRepository):
        self.repo = repo
        self.account_repo = account_repo

    async def follow(self, follower_id: int, vlogger_id: int) -> None:
        if follower_id == vlogger_id:
            raise ValueError("cannot follow yourself")
        if await self.account_repo.find_by_id(follower_id) is None:
            raise ValueError("follower not found")
        if await self.account_repo.find_by_id(vlogger_id) is None:
            raise ValueError("vlogger not found")
        if await self.repo.is_followed(follower_id, vlogger_id):
            raise ValueError("already followed")
        await self.repo.follow(follower_id, vlogger_id)

    async def unfollow(self, follower_id: int, vlogger_id: int) -> None:
        if not await self.repo.is_followed(follower_id, vlogger_id):
            raise ValueError("not followed yet")
        await self.repo.unfollow(follower_id, vlogger_id)

    async def get_all_followers(self, vlogger_id: int) -> tuple[list[dict], int]:
        followers = await self.repo.get_all_followers(vlogger_id)
        count = await self.repo.count_followers(vlogger_id)
        return followers, count

    async def get_all_vloggers(self, follower_id: int) -> tuple[list[dict], int]:
        vloggers = await self.repo.get_all_vloggers(follower_id)
        count = await self.repo.count_vloggers(follower_id)
        return vloggers, count

    async def get_counts(self, account_id: int) -> tuple[int, int]:
        return (
            await self.repo.count_followers(account_id),
            await self.repo.count_vloggers(account_id),
        )
