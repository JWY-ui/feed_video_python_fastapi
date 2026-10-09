import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.database import get_db
from app.middleware.jwt_auth import get_current_user
from app.config import settings
from app.agent_v2.schemas import (
    ChatRequest, CreateConversationResponse,
    DeleteConversationRequest,
    ListConversationsRequest, ListConversationsResponse,
    ConversationListItem,
    HistoryRequest, HistoryResponse, HistoryItem,
)
from app.agent_v2.service import ChatService

logger = logging.getLogger("agent_v2.router")


async def check_agent_enabled():
    if not settings.openai_api_key:
        raise HTTPException(status_code=503,
                            detail="Agent not configured: OPENAI_API_KEY is not set")


router = APIRouter(prefix="/agent", tags=["9. Agent"],
                   dependencies=[Depends(check_agent_enabled)])


@router.post("/chat")
async def chat(
    req: ChatRequest,
    user: dict = Depends(get_current_user),
):
    service = ChatService()
    return EventSourceResponse(
        service.chat_stream(user["account_id"], user.get("username", ""),
                            req.thread_id, req.message)
    )


@router.post("/create", response_model=CreateConversationResponse)
async def create_conversation(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = ChatService(db)
    conv = await service.create_conversation(user["account_id"])
    return CreateConversationResponse(
        thread_id=conv["thread_id"],
        title=conv["title"],
    )


@router.post("/delete")
async def delete_conversation(
    req: DeleteConversationRequest,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = ChatService(db)
    try:
        await service.delete_conversation(req.thread_id, user["account_id"])
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"message": "deleted"}


@router.post("/conversations", response_model=ListConversationsResponse)
async def list_conversations(
    req: ListConversationsRequest,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = ChatService(db)
    convs = await service.list_conversations(
        user["account_id"], req.limit, req.before_id,
    )
    items = [
        ConversationListItem(
            id=c["id"], thread_id=c["thread_id"],
            title=c["title"],
            created_at=c["created_at"].isoformat(),
            updated_at=c["updated_at"].isoformat(),
        )
        for c in convs
    ]
    return ListConversationsResponse(
        conversations=items,
        has_more=len(items) == req.limit,
    )


@router.post("/history", response_model=HistoryResponse)
async def get_history(
    req: HistoryRequest,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = ChatService(db)
    try:
        msgs = await service.get_history(
            user["account_id"], req.thread_id,
            req.limit, req.before_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    items = [
        HistoryItem(
            id=m["id"], role=m["role"], content=m["content"],
            created_at=m["created_at"].isoformat(),
        )
        for m in msgs
    ]
    return HistoryResponse(
        messages=items,
        has_more=len(items) == req.limit,
    )
