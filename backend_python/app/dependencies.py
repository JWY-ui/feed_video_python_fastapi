# -*- coding: utf-8 -*-
"""
Shared dependency injection -- Account module Repo -> Service dependency chain.

How FastAPI Depends resolves recursively:

  Router declares:
    async def register(service: AccountService = Depends(get_account_service))

  FastAPI sees Depends(get_account_service) and automatically:
    1. Calls get_account_service()
    2. Finds it also needs Depends(get_account_repo)
    3. Calls get_account_repo()
    4. Finds it also needs Depends(get_db)
    5. Calls get_db() -> creates AsyncSession -> passes to get_account_repo
    6. get_account_repo(session) -> returns AccountRepository -> passes to get_account_service
    7. get_account_service(repo) -> returns AccountService -> injects into Router

  -> Router's `service` param is the fully assembled AccountService instance.

Why Depends instead of manually new-ing in main.py?
  - Each request gets an independent dependency chain (thread-safe)
  - Unit tests can swap Depends (inject mock objects)
  - No need to maintain assembly order in main.py

Other modules (Video, Like, Comment, etc.) define their dependency chains
inline in their own Router files since they don't need cross-module sharing.
"""
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.repositories.account_repo import AccountRepository
from app.services.account_service import AccountService


def get_account_repo(db: AsyncSession = Depends(get_db)) -> AccountRepository:
    """
    Create AccountRepository instance.

    One call per request -> one independent Repo per request -> bound to current session.
    """
    return AccountRepository(db)


def get_account_service(repo: AccountRepository = Depends(get_account_repo)) -> AccountService:
    """
    Create AccountService instance.

    Dependency chain: get_db -> get_account_repo -> get_account_service
    FastAPI resolves it recursively -- no manual assembly needed.
    """
    return AccountService(repo)
