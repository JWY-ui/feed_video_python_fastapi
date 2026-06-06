# -*- coding: utf-8 -*-
"""
Account module -- Pydantic request/response models.

Each endpoint's input and output is defined here. FastAPI auto-handles:
  1. JSON body -> Pydantic object (auto-validate type, length, required)
  2. Pydantic object -> JSON response (response_model auto-filters extra fields)
  3. Auto-generate Swagger docs

Why separate Model and Schema?
  - Model (SQLAlchemy): describes DB table structure, includes all fields (password, token)
  - Schema (Pydantic): describes API request/response format, only exposes needed fields (password never returned)
  Combining them causes security issues (password leak) and API coupling.
"""
from pydantic import BaseModel, Field


# ---- Request models ----

class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=255, description="Username")
    password: str = Field(..., min_length=6, max_length=72, description="Password, bcrypt 72-byte limit")


class LoginRequest(BaseModel):
    username: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str
    access_token: str   # Expired access token, used to extract account_id


class ChangePasswordRequest(BaseModel):
    username: str
    old_password: str
    new_password: str = Field(..., min_length=6, max_length=72)


class FindByIDRequest(BaseModel):
    id: int


class FindByUsernameRequest(BaseModel):
    username: str


class RenameRequest(BaseModel):
    new_username: str = Field(..., min_length=1, max_length=255)


class UpdateProfileRequest(BaseModel):
    avatar_url: str | None = None
    bio: str | None = None


class GetProfileRequest(BaseModel):
    account_id: int


# ---- Response models ----

class AccountInfo(BaseModel):
    """
    Public user info -- note: no password or token fields.

    With response_model=AccountInfo, FastAPI auto-filters out extra fields
    (password, token, refresh_token) from the Model, ensuring sensitive data never leaks.
    """
    id: int
    username: str
    avatar_url: str | None = None
    bio: str | None = None


class LoginResponse(BaseModel):
    """Login / refresh token response."""
    token: str
    refresh_token: str
    account_id: int
    username: str


class GetProfileResponse(BaseModel):
    """User profile: basic info + stats."""
    account: AccountInfo
    video_count: int
    total_likes: int
    follower_count: int
    vlogger_count: int
