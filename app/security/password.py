"""密码哈希工具。

使用 stdlib `hashlib.pbkdf2_hmac`（sha256, 600k 迭代），无外部依赖。
格式：`pbkdf2_sha256$<iterations>$<salt_b64>$<hash_b64>`，与 Django 兼容。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os

_ALGO = "pbkdf2_sha256"
_ITERATIONS = 600_000
_SALT_BYTES = 16
_KEY_BYTES = 32


def hash_password(password: str) -> str:
    salt = os.urandom(_SALT_BYTES)
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _ITERATIONS, _KEY_BYTES)
    return f"{_ALGO}${_ITERATIONS}${base64.b64encode(salt).decode()}${base64.b64encode(key).decode()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algo, iters_str, salt_b64, key_b64 = encoded.split("$")
    except ValueError:
        return False
    if algo != _ALGO:
        return False
    try:
        iterations = int(iters_str)
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(key_b64)
    except Exception:
        return False
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations, len(expected))
    return hmac.compare_digest(key, expected)


__all__ = ["hash_password", "verify_password"]
