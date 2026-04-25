from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from typing import Any

from .config import PASSWORD_HASH_ROUNDS, SESSION_SECRET


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("utf-8").rstrip("=")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    derived = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PASSWORD_HASH_ROUNDS,
    )
    return f"{_b64encode(salt)}${_b64encode(derived)}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        salt_encoded, digest_encoded = stored_hash.split("$", 1)
        salt = _b64decode(salt_encoded)
        expected = _b64decode(digest_encoded)
    except ValueError:
        return False

    candidate = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PASSWORD_HASH_ROUNDS,
    )
    return hmac.compare_digest(candidate, expected)


def create_session_token(payload: dict[str, Any]) -> str:
    payload_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    payload_token = _b64encode(payload_bytes)
    signature = hmac.new(
        SESSION_SECRET.encode("utf-8"),
        payload_token.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return f"{payload_token}.{_b64encode(signature)}"


def decode_session_token(token: str) -> dict[str, Any] | None:
    try:
        payload_token, signature_token = token.split(".", 1)
    except ValueError:
        return None

    expected_signature = hmac.new(
        SESSION_SECRET.encode("utf-8"),
        payload_token.encode("utf-8"),
        hashlib.sha256,
    ).digest()

    if not hmac.compare_digest(_b64encode(expected_signature), signature_token):
        return None

    try:
        decoded = _b64decode(payload_token)
        payload = json.loads(decoded.decode("utf-8"))
    except (json.JSONDecodeError, ValueError, UnicodeDecodeError):
        return None

    return payload if isinstance(payload, dict) else None

