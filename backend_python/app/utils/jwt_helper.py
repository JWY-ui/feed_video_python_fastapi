# -*- coding: utf-8 -*-
"""
JWT utilities -- Access Token and Refresh Token generation and parsing.

Dual token mechanism:

  Access Token (JWT, 15 minutes)
    - Sent with every HTTP request in Authorization: Bearer <token> header
    - Server decodes to get account_id and username, no DB lookup needed
    - 15 min short lifetime: if leaked, attack window is only 15 minutes

  Refresh Token (random string, 7 days)
    - Used only when Access Token expires, to get a new Access Token
    - Not sent with every request, lower leak risk
    - Stored in DB, can be revoked anytime (e.g. on suspicious login)

HS256 algorithm:
  - Symmetric: sign and verify with same key (settings.jwt_secret)
  - Good for monoliths; microservices should use RS256 (public/private keys)
"""
import secrets
from datetime import datetime, timedelta

from jose import JWTError, jwt

from app.config import settings

# Access Token expiry in minutes -- 15 min is the sweet spot between security and UX.
ACCESS_TOKEN_EXPIRE_MINUTES = 15


def create_access_token(account_id: int, username: str) -> str:
    """
    Generate Access Token (JWT).

    Args:
      account_id: user ID, available directly from JWT payload, no DB lookup needed
      username: username, used when publishing videos, no JOIN needed

    Returns:
      JWT string, format: header.payload.signature
      Stored in localStorage or cookie by frontend.

    JWT payload fields:
      - account_id / username : custom fields, business data
      - exp : expiration time, jwt.decode() auto-validates
      - iat : issued at
      - nbf : not before, set equal to iat, effective immediately
    """
    now = datetime.now(datetime.UTC)
    payload = {
        "account_id": account_id,
        "username": username,
        "exp": now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
        "iat": now,
        "nbf": now,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def create_refresh_token() -> str:
    """
    Generate Refresh Token -- NOT a JWT, just a 64-char random hex string.

    Why not JWT?
      Refresh Token only has one use: "exchange for new Access Token".
      No need to carry business data. Random string is shorter, easier to
      store securely, easier to look up and revoke in DB.

    secrets.token_hex(32) = 32 bytes random -> 64 char hex string.
    Secure enough: 2^256 possibilities, brute-force impractical.
    """
    return secrets.token_hex(32)


def decode_token(token_string: str) -> dict:
    """
    Parse and verify Access Token.

    Args:
      token_string: JWT extracted from Authorization: Bearer <token> header

    Returns:
      {"account_id": int, "username": str}
      Both fields come from JWT payload, no DB lookup needed.

    Errors:
      ExpiredSignatureError : Token expired (exp < now)
      JWTError              : Bad signature, malformed, nbf not reached, etc.

    jwt.decode() internally:
      1. Verifies signature with settings.jwt_secret (HMAC-SHA256)
      2. Checks if exp has passed
      3. Checks if nbf has been reached
      All automatic, no manual coding needed.
    """
    payload = jwt.decode(token_string, settings.jwt_secret, algorithms=["HS256"])
    return {
        "account_id": payload["account_id"],
        "username": payload["username"],
    }


def decode_token_skip_expiry(token_string: str) -> dict:
    """
    Decode JWT without validating expiration -- for Refresh endpoint only.

    When Access Token expires, client sends it along with Refresh Token.
    Server extracts account_id from the expired token, then looks up
    the Refresh Token in DB for validation.

    Only skips exp validation; signature validation still runs -- prevents forged tokens.
    """
    payload = jwt.decode(
        token_string, settings.jwt_secret, algorithms=["HS256"],
        options={"verify_exp": False},  # don't check expiry, do check everything else (signature, nbf, etc.)
    )
    return {
        "account_id": payload["account_id"],
        "username": payload["username"],
    }
