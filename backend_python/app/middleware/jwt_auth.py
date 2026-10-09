# -*- coding: utf-8 -*-
"""
JWT authentication (get_current_user hard-auth / get_optional_user soft-auth).

Operates entirely on dicts, never exposes SQLAlchemy Models.
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal, get_db
from app.repositories.account_repo import AccountRepository
from app.utils import jwt_helper

security = HTTPBearer(auto_error=False)


async def _authenticate(token_string: str, db: AsyncSession) -> dict:
    try:
        payload = jwt_helper.decode_token(token_string)
    except jwt_helper.JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="invalid or expired token")

    repo = AccountRepository(db)
    cached = await repo.get_token_cache(payload["account_id"])

    if cached is None or cached != token_string:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="token has been revoked")

    return {"account_id": payload["account_id"], "username": payload["username"]}


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="missing authorization header")
    return await _authenticate(credentials.credentials, db)


async def get_current_user_stateless(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> dict:
    """
    Authenticate WITHOUT holding a DB session past this call. For SSE only.

    get_current_user depends on get_db, a yield-dependency whose session lives
    until the response finishes. An SSE response never finishes, so that session
    -- and, whenever Redis is unavailable and the token cache misses, the pooled
    MySQL connection it holds -- would be pinned for the whole life of the
    connection. pool_size(10) + max_overflow(20) means ~30 open streams would
    stall every other request in the app.

    This is a plain (non-generator) dependency, so the `async with` block exits
    and the connection is returned to the pool BEFORE the endpoint returns the
    StreamingResponse. Auth is therefore complete before the first byte streams.
    """
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="missing authorization header")
    async with AsyncSessionLocal() as db:
        return await _authenticate(credentials.credentials, db)


async def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> dict | None:
    if credentials is None:
        return None
    return await _authenticate(credentials.credentials, db)
