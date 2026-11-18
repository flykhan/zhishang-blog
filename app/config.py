"""应用配置：全部来自环境变量，带安全缺省值。"""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULT_DB_PATH = "./data/blog.db"
DEFAULT_SITE_URL = "http://localhost:8080"


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def resolve_secret_key(db_path: str) -> str:
    """优先使用环境变量；否则生成并持久化到数据库同目录的 .secret_key。

    持久化可以保证容器重启后会话仍然有效。
    """
    configured = os.environ.get("SECRET_KEY", "").strip()
    if configured:
        return configured

    key_file = Path(db_path).expanduser().resolve().parent / ".secret_key"
    try:
        existing = key_file.read_text(encoding="utf-8").strip()
        if existing:
            return existing
    except OSError:
        pass

    generated = secrets.token_hex(32)
    try:
        key_file.parent.mkdir(parents=True, exist_ok=True)
        key_file.write_text(generated + "\n", encoding="utf-8")
        os.chmod(key_file, 0o600)
    except OSError:
        # 只读文件系统等场景：退化为每次启动随机（会话不跨重启）
        pass
    return generated


@dataclass(frozen=True)
class Settings:
    db_path: str
    secret_key: str
    admin_username: str
    admin_password: str
    site_url: str
    site_tz: str
    allow_comments: bool
    cookie_secure: bool
    session_max_age: int
    port: int
    trust_proxy: bool
    max_body_bytes: int
    max_import_bytes: int

    @property
    def timezone(self) -> ZoneInfo:
        try:
            return ZoneInfo(self.site_tz)
        except (ZoneInfoNotFoundError, ValueError):
            return ZoneInfo("UTC")

    @property
    def site_url_base(self) -> str:
        return self.site_url.rstrip("/")


_DB_PATH = os.environ.get("DB_PATH", DEFAULT_DB_PATH)

settings = Settings(
    db_path=_DB_PATH,
    secret_key=resolve_secret_key(_DB_PATH),
    admin_username=os.environ.get("ADMIN_USERNAME", "admin").strip() or "admin",
    admin_password=os.environ.get("ADMIN_PASSWORD", "").strip(),
    site_url=os.environ.get("SITE_URL", DEFAULT_SITE_URL),
    site_tz=os.environ.get("SITE_TZ", "Asia/Shanghai"),
    allow_comments=_env_bool("ALLOW_COMMENTS", True),
    cookie_secure=_env_bool("COOKIE_SECURE", False),
    session_max_age=_env_int("SESSION_MAX_AGE", 604800),
    port=_env_int("PORT", 8000),
    trust_proxy=_env_bool("TRUST_PROXY", False),
    max_body_bytes=_env_int("MAX_BODY_BYTES", 1_048_576),
    max_import_bytes=_env_int("MAX_IMPORT_BYTES", 26_214_400),
)
