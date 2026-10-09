# -*- coding: utf-8 -*-
"""
Direct-message business logic.

Exists mainly for consistency: every other module goes Router -> Service -> Repo,
and message was the one place the router called the repository directly. It is
also the seam the agent tools go through, which is why the content guard lives
here rather than only in the request schema (the schema does not protect a call
made from inside the process).
"""
from app.repositories.message_repo import MessageRepository


class MessageService:

    def __init__(self, repo: MessageRepository):
        self.repo = repo

    async def send(self, from_id: int, to_id: int, content: str) -> dict:
        """
        Store a direct message.

        Returns the stored row as a dict (`created_at` already normalized to
        aware UTC by the repository).
        """
        text = content.strip()
        if not text:
            raise ValueError("content is required")
        if to_id <= 0:
            raise ValueError("invalid recipient")
        return await self.repo.send(from_id, to_id, text)

    async def list(self, user_id: int, peer_id: int, limit: int = 50) -> list[dict]:
        """Both directions of the conversation, newest first."""
        return await self.repo.list(user_id, peer_id, limit)
