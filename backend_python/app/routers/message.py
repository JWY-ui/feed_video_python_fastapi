# -*- coding: utf-8 -*-
"""Message routes -- 2 endpoints, all require login."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.jwt_auth import get_current_user
from app.repositories.message_repo import MessageRepository
from app.schemas.message import SendMessageRequest, ListMessagesRequest, ListMessagesResponse

router = APIRouter(dependencies=[Depends(get_current_user)])


@router.post("/send")
async def send_message(req: SendMessageRequest,
                       current_user: dict = Depends(get_current_user),
                       db: AsyncSession = Depends(get_db)):
    repo = MessageRepository(db)
    msg = await repo.send(current_user["account_id"], req.to_id, req.content)
    return msg


@router.post("/list", response_model=ListMessagesResponse)
async def list_messages(req: ListMessagesRequest,
                        current_user: dict = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    repo = MessageRepository(db)
    msgs = await repo.list(current_user["account_id"], req.peer_id)
    return ListMessagesResponse(messages=msgs)
