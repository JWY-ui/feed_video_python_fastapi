# -*- coding: utf-8 -*-
"""Message routes -- 2 endpoints, all require login."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.jwt_auth import get_current_user
from app.repositories.message_repo import MessageRepository
from app.schemas.message import SendMessageRequest, ListMessagesRequest, ListMessagesResponse
from app.services.message_service import MessageService

router = APIRouter(dependencies=[Depends(get_current_user)])


def _get_message_service(db: AsyncSession = Depends(get_db)) -> MessageService:
    return MessageService(MessageRepository(db))


@router.post("/send")
async def send_message(req: SendMessageRequest,
                       current_user: dict = Depends(get_current_user),
                       service: MessageService = Depends(_get_message_service)):
    try:
        return await service.send(current_user["account_id"], req.to_id, req.content)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/list", response_model=ListMessagesResponse)
async def list_messages(req: ListMessagesRequest,
                        current_user: dict = Depends(get_current_user),
                        service: MessageService = Depends(_get_message_service)):
    msgs = await service.list(current_user["account_id"], req.peer_id)
    return ListMessagesResponse(messages=msgs)
