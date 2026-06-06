# -*- coding: utf-8 -*-
"""
JWT authentication (get_current_user hard-auth / get_optional_user soft-auth).

Operates entirely on dicts, never exposes SQLAlchemy Models.
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
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


async def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> dict | None:
    if credentials is None:
        return None
    return await _authenticate(credentials.credentials, db)
