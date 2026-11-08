"""管理员鉴权 — 修正版规格 v2 §8。

单管理员：ADMIN_EMAIL + ADMIN_PASSWORD_HASH（bcrypt，$2a$/$2b$；
为兼容本地开发，也接受 pbkdf2_sha256$iterations$salt$hash 格式）。
登录成功签发有状态签名的会话 Cookie：admin_session =
base64url({"email","exp"}) + "." + HMAC-SHA256(JWT_SECRET)。
Cookie：HttpOnly + SameSite=Lax，Secure 只在 SECURE_COOKIE=1 时开
（本地 http 开发不开，否则浏览器不存 Cookie）。
环境变量在每次请求时读取，不在 import 时绑定，方便测试注入。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time

from fastapi import Cookie, Depends, HTTPException

COOKIE_NAME = "admin_session"
SESSION_TTL_SECONDS = 12 * 3600


def _b64e(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64d(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def hash_password_pbkdf2(password: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 200_000)
    return f"pbkdf2_sha256$200000${salt}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    if not stored:
        return False
    if stored.startswith(("$2a$", "$2b$", "$2y$")):
        try:
            import bcrypt  # type: ignore
        except ImportError:
            return False
        try:
            return bcrypt.checkpw(password.encode(), stored.encode())
        except Exception:
            return False
    if stored.startswith("pbkdf2_sha256$"):
        try:
            _, iters, salt, hexhash = stored.split("$")
            dk = hashlib.pbkdf2_hmac(
                "sha256", password.encode(), bytes.fromhex(salt), int(iters)
            )
            return hmac.compare_digest(dk.hex(), hexhash)
        except Exception:
            return False
    return False


def _secret() -> str:
    return os.environ.get("JWT_SECRET", "")


def make_session_token(email: str) -> str:
    secret = _secret()
    if not secret:
        raise RuntimeError("未配置 JWT_SECRET，无法签发会话")
    payload = {"email": email, "exp": int(time.time()) + SESSION_TTL_SECONDS}
    raw = json.dumps(payload, separators=(",", ":")).encode()
    sig = hmac.new(secret.encode(), raw, hashlib.sha256).digest()
    return _b64e(raw) + "." + _b64e(sig)


def verify_session_token(token: str | None) -> str | None:
    """返回邮箱，非法/过期返回 None。"""
    if not token or "." not in token:
        return None
    secret = _secret()
    if not secret:
        return None
    try:
        raw_b64, sig_b64 = token.rsplit(".", 1)
        raw = _b64d(raw_b64)
        expect = hmac.new(secret.encode(), raw, hashlib.sha256).digest()
        if not hmac.compare_digest(expect, _b64d(sig_b64)):
            return None
        payload = json.loads(raw.decode())
        if int(payload["exp"]) < int(time.time()):
            return None
        return str(payload["email"])
    except Exception:
        return None


def check_admin_credentials(email: str, password: str) -> bool:
    admin_email = os.environ.get("ADMIN_EMAIL", "")
    admin_hash = os.environ.get("ADMIN_PASSWORD_HASH", "")
    if not admin_email or not admin_hash:
        return False
    if email != admin_email:
        return False
    return verify_password(password, admin_hash)


def require_admin(admin_session: str | None = Cookie(default=None, alias=COOKIE_NAME)) -> str:
    email = verify_session_token(admin_session)
    if email is None:
        raise HTTPException(status_code=401, detail="未登录或会话已过期")
    return email
