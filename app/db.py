"""SQLite 连接、建表与首次初始化种子数据。"""

from __future__ import annotations

import logging
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from .auth import hash_password
from .config import settings
from .utils import utc_now_iso

logger = logging.getLogger("paper.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS posts (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    slug         TEXT NOT NULL UNIQUE,
    title        TEXT NOT NULL,
    summary      TEXT NOT NULL DEFAULT '',
    content_md   TEXT NOT NULL DEFAULT '',
    tags         TEXT NOT NULL DEFAULT '',
    status       TEXT NOT NULL DEFAULT 'draft',
    views        INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    published_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_posts_status_published
    ON posts (status, published_at DESC);

CREATE TABLE IF NOT EXISTS comments (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id    INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    author     TEXT NOT NULL,
    email      TEXT NOT NULL DEFAULT '',
    content    TEXT NOT NULL,
    status     TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL,
    ip         TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_comments_post_status
    ON comments (post_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_comments_status_created
    ON comments (status, created_at DESC);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

DEFAULT_SETTINGS = {
    "site_title": "纸上",
    "site_subtitle": "写字的地方",
    "site_description": "一个安静的角落，记录阅读、代码与生活。",
    "author_name": "纸上",
    "author_bio": "写字的人。",
    "footer_text": "© {year} 纸上 · 用 FastAPI 与 SQLite 手工打造",
    "about_md": (
        "# 关于\n\n"
        "这里是一个安静的角落，用来存放一些值得留下来的文字。\n\n"
        "## 关于这个站\n\n"
        "- 用 Markdown 写作，专注内容本身\n"
        "- 支持草稿、标签、归档与站内搜索\n"
        "- 评论先进入待审队列，由站长决定是否公开\n\n"
        "> 保持好奇，保持记录。\n"
    ),
    "posts_per_page": "8",
    "allow_comments": "1" if settings.allow_comments else "0",
}

WELCOME_MD = """\
# 你好，世界

欢迎来到 **纸上**——一个用 FastAPI + SQLite 手工搭起来的安静博客。

## 你能在这里做什么

- 用 Markdown 写文章，支持代码块、表格和引用
- 先把想法存成草稿，准备好了再发布
- 用标签、归档和搜索整理自己的文字
- 评论会先进入待审核队列，由你决定是否公开

## 一段示例代码

```python
def hello(name: str) -> str:
    return f"你好，{name}"
```

> 写作是整理思绪的方式。愿你在这里留下一些真实的东西。

## 下一步

1. 进入 `/admin` 登录后台（默认账号见 README）
2. 在「设置」里改掉站点标题、副标题和页脚
3. 写第一篇文章，然后把这篇示例删掉

— 纸上
"""

WELCOME_SUMMARY = (
    "欢迎来到纸上——一个用 FastAPI + SQLite 手工搭起来的安静博客。"
    "这里是一个起点，也是一份写作与排版能力的示例。"
)


@contextmanager
def get_conn():
    """每次请求一个短连接；WAL 模式下并发读写足够用。"""
    Path(settings.db_path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(settings.db_path, timeout=15)
    con.row_factory = sqlite3.Row
    try:
        con.execute("PRAGMA foreign_keys = ON")
        con.execute("PRAGMA busy_timeout = 5000")
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def connect() -> sqlite3.Connection:
    """给需要手动管理生命周期的地方使用（例如后台脚本）。"""
    Path(settings.db_path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(settings.db_path, timeout=15)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA journal_mode = WAL")
    con.execute("PRAGMA busy_timeout = 5000")
    return con


def init_db() -> None:
    """幂等初始化：建表 + 补默认设置 + 首次创建管理员与示例文章。"""
    with get_conn() as con:
        con.execute("PRAGMA journal_mode = WAL")
        con.executescript(SCHEMA)
        _seed(con)


def _seed(con: sqlite3.Connection) -> None:
    for key, value in DEFAULT_SETTINGS.items():
        con.execute(
            "INSERT OR IGNORE INTO settings(key, value) VALUES(?, ?)", (key, value)
        )

    if con.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"] == 0:
        con.execute(
            "INSERT INTO users(username, password_hash, created_at) VALUES(?, ?, ?)",
            (settings.admin_username, hash_password(settings.admin_password), utc_now_iso()),
        )
        logger.info("已创建管理员账号：%s", settings.admin_username)

    if con.execute("SELECT COUNT(*) AS c FROM posts").fetchone()["c"] == 0:
        now = utc_now_iso()
        con.execute(
            "INSERT INTO posts(slug, title, summary, content_md, tags, status, views,"
            " created_at, updated_at, published_at) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "hello-world",
                "你好，世界",
                WELCOME_SUMMARY,
                WELCOME_MD,
                "随笔,公告",
                "published",
                0,
                now,
                now,
                now,
            ),
        )
        logger.info("已写入示例文章 hello-world")
