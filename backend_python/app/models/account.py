# -*- coding: utf-8 -*-
"""
User account table (accounts)

Design notes:
  1. token / refresh_token stored in DB -- JWT is stateless but needs "active revocation".
     On logout/password-change, clear these fields; old JWT is invalidated immediately.
  2. password stores bcrypt hash, never plaintext.
     Even if DB is leaked, attacker cannot recover original passwords.
  3. username has unique index -- high-frequency lookup field for register and login.

Used by queries:
  - Register: INSERT + unique index conflict detection
  - Login: SELECT WHERE username = ?
  - Auth: SELECT WHERE id = ? (high frequency, PK lookup is fastest)
  - Token refresh: full table scan find_all (low frequency, future: Redis)
  - Feed: does NOT JOIN accounts table (Video redundantly stores username)
"""
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Account(Base):
    __tablename__ = "accounts"

    # PK, auto-increment. session.get() on PK is fastest (checks identity map first).
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # Username, unique constraint. Used by both login and register lookups.
    username: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    # bcrypt-hashed password (60 chars + salt). Never exposed in API responses.
    password: Mapped[str] = mapped_column(String(255), nullable=False)
    # Current valid access token (JWT). Cleared on logout/password-change -> instant revocation.
    token: Mapped[str] = mapped_column(String(512), default="")
    # Current valid refresh token (random hex string, 7-day validity).
    refresh_token: Mapped[str] = mapped_column(String(512), default="")
    # Avatar URL. Nullable (new users have no avatar).
    avatar_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # Bio, max 255 chars.
    bio: Mapped[str | None] = mapped_column(String(255), nullable=True)
