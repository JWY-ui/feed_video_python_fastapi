from pydantic import BaseModel


class ChatRequest(BaseModel):
    thread_id: str = ""
    message: str


class CreateConversationResponse(BaseModel):
    thread_id: str
    title: str = ""


class DeleteConversationRequest(BaseModel):
    thread_id: str


class ConversationListItem(BaseModel):
    id: int
    thread_id: str
    title: str
    created_at: str
    updated_at: str


class ListConversationsRequest(BaseModel):
    before_id: int | None = None
    limit: int = 20


class ListConversationsResponse(BaseModel):
    conversations: list[ConversationListItem]
    has_more: bool


class HistoryRequest(BaseModel):
    thread_id: str
    before_id: int | None = None
    limit: int = 20


class HistoryItem(BaseModel):
    id: int
    role: str
    content: str
    created_at: str


class HistoryResponse(BaseModel):
    messages: list[HistoryItem]
    has_more: bool
