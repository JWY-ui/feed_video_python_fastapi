# -*- coding: utf-8 -*-
"""
Password utilities -- bcrypt hashing and verification.

Why bcrypt instead of SHA256?
  1. bcrypt has built-in salt -- same password produces different hash each time.
     Attackers can't use rainbow tables; must brute-force each password individually.
  2. bcrypt has adjustable cost (computation rounds) -- default 12 rounds.
     Each extra round doubles crack time. Can increase as hardware improves.
  3. bcrypt is deliberately slow -- normal login ~hundreds of ms,
     brute-force takes centuries.

bcrypt limitation:
  Max 72 bytes input. Extra-long passwords are truncated to first 72 bytes.
  Both frontend and Pydantic schema already limit password length;
  the truncation here is the last line of defense.
"""
import bcrypt


def hash_password(password: str) -> str:
    """
    Hash plaintext password with bcrypt.

    Args:
      password: user's plaintext password (e.g. "123456")

    Returns:
      bcrypt hash string, format: $2b$12$salt...hash...
      Safe to store directly in DB password field.

    Process:
      1. Encode password to bytes (bcrypt only works with bytes)
      2. Truncate to first 72 bytes (bcrypt input limit)
      3. bcrypt.gensalt() generates random salt
      4. bcrypt.hashpw() hashes password with salt
      5. Decode back to str for DB storage
    """
    pwd_bytes = password.encode("utf-8")[:72]
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pwd_bytes, salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify plaintext password matches the stored hash.

    Args:
      plain_password: user's input at login
      hashed_password: bcrypt hash stored in DB (e.g. "$2b$12$...")

    Returns:
      True = correct password, False = wrong password.

    No need to extract salt manually -- bcrypt.checkpw auto-parses
    salt from the hashed_password string.
    Salt is embedded in bcrypt output: $2b$12$<22-char-salt><31-char-hash>
    """
    pwd_bytes = plain_password.encode("utf-8")[:72]
    hashed_bytes = hashed_password.encode("utf-8")
    return bcrypt.checkpw(pwd_bytes, hashed_bytes)
