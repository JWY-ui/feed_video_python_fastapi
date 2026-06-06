# -*- coding: utf-8 -*-
"""Video module -- Pydantic request/response models."""
from pydantic import BaseModel, Field


# --- Video publish ---
class PublishVideoRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: str = ""
    play_url: str = Field(..., min_length=1)
    cover_url: str = Field(..., min_length=1)


class VideoInfo(BaseModel):
    """Video detail response."""
    id: int
    author_id: int
    username: str
    title: str
    description: str | None = None
    play_url: str
    cover_url: str
    create_time: str  # ISO format time string
    likes_count: int
    popularity: int


class ListByAuthorIDRequest(BaseModel):
    author_id: int


class GetDetailRequest(BaseModel):
    id: int


# --- Upload responses ---
class UploadResponse(BaseModel):
    url: str
    play_url: str | None = None  # uploadCover does not return play_url


class CoverUploadResponse(BaseModel):
    url: str
    cover_url: str


# --- Chunked upload ---
class InitChunkRequest(BaseModel):
    filename: str = Field(..., min_length=1)
    file_size: int = Field(..., gt=0)
    chunk_size: int = Field(..., gt=0)
    total_chunks: int = Field(..., gt=0)
    file_hash: str = Field(..., min_length=1)


class InitChunkResponse(BaseModel):
    upload_id: str
    uploaded_chunks: list[int]  # Already uploaded chunk indices (for resume)


class ChunkStatusRequest(BaseModel):
    upload_id: str = Field(..., min_length=1)


class ChunkStatusResponse(BaseModel):
    upload_id: str
    uploaded_chunks: list[int]
    total_chunks: int


class CompleteChunkRequest(BaseModel):
    upload_id: str = Field(..., min_length=1)
