"""认证与会话：PBKDF2 密码哈希、HMAC 签名 Cookie 会话、CSRF、登录限流。

不依赖任何服务端会话存储，重启后签名密钥不变即可保持登录态。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from collections import defaultdict, deque
from threading import Lock

from fastapi import Request, Response

from .config import settings

SESSION_COOKIE = "blog_session"
LOGIN_CSRF_COOKIE = "blog_login_csrf"
PBKDF2_ITERATIONS = 260_000

# 登录失败限流：10 分钟内最多 8 次
LOGIN_WINDOW_SECONDS = 600
LOGIN_MAX_FAILURES = 8

# 评论提交限流：60 秒内最多 5 条
COMMENT_WINDOW_SECONDS = 60
COMMENT_MAX = 5


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS
    )
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iterations, salt_hex, digest_hex = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
        actual = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, int(iterations)
        )
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError, AttributeError):
        return False


# ---------------------------------------------------------------- 会话 Cookie


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _sign(raw: bytes) -> str:
    return hmac.new(settings.secret_key.encode("utf-8"), raw, hashlib.sha256).hexdigest()


def create_session(user_id: int, username: str, session_version: int = 0) -> str:
    now = int(time.time())
    payload = {
        "uid": user_id,
        "u": username,
        "sv": int(session_version),
        "csrf": secrets.token_urlsafe(24),
        "iat": now,
        "exp": now + settings.session_max_age,
    }
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return _b64encode(raw) + "." + _sign(raw)


def load_session(request: Request) -> dict | None:
    token = request.cookies.get(SESSION_COOKIE)
    if not token or "." not in token:
        return None
    payload_b64, signature = token.rsplit(".", 1)
    try:
        raw = _b64decode(payload_b64)
    except (ValueError, TypeError):
        return None
    try:
        valid_signature = hmac.compare_digest(
            signature.encode("utf-8", "surrogatepass"), _sign(raw).encode("ascii")
        )
    except (UnicodeError, TypeError):
        return None
    if not valid_signature:
        return None
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    if int(data.get("exp", 0)) < int(time.time()):
        return None
    return data


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=settings.session_max_age,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")


def new_login_csrf() -> str:
    return secrets.token_urlsafe(24)


def client_ip(request: Request) -> str:
    """取客户端 IP；仅在显式信任反向代理时使用 X-Forwarded-For。"""
    if settings.trust_proxy:
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            candidate = forwarded.split(",")[0].strip()
            if candidate:
                return candidate
    return request.client.host if request.client else "unknown"


# ---------------------------------------------------------------- 限流


class _SlidingWindowLimiter:
    def __init__(self, window_seconds: int, max_events: int):
        self.window = window_seconds
        self.max_events = max_events
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def allowed(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            events = self._events[key]
            while events and now - events[0] > self.window:
                events.popleft()
            return len(events) < self.max_events

    def record(self, key: str) -> None:
        with self._lock:
            self._events[key].append(time.monotonic())

    def reset(self, key: str) -> None:
        with self._lock:
            self._events.pop(key, None)


_login_limiter = _SlidingWindowLimiter(LOGIN_WINDOW_SECONDS, LOGIN_MAX_FAILURES)
_comment_limiter = _SlidingWindowLimiter(COMMENT_WINDOW_SECONDS, COMMENT_MAX)


def login_allowed(ip: str) -> bool:
    return _login_limiter.allowed(ip)


def record_login_failure(ip: str) -> None:
    _login_limiter.record(ip)


def clear_login_failures(ip: str) -> None:
    _login_limiter.reset(ip)


def comment_allowed(ip: str) -> bool:
    return _comment_limiter.allowed(ip)


def record_comment(ip: str) -> None:
    _comment_limiter.record(ip)
