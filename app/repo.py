"""数据访问层：文章、评论、设置、用户的全部 SQL 集中在这里。"""

from __future__ import annotations

import secrets
import sqlite3
from collections import Counter
from datetime import datetime, timezone

from . import db
from .utils import (
    excerpt,
    local_year,
    normalize_tags,
    plain_text,
    reading_time,
    slugify,
    taglist,
    utc_now_iso,
)

POST_STATUSES = ("draft", "published")
COMMENT_STATUSES = ("pending", "approved")


def _post_dict(row: sqlite3.Row) -> dict:
    post = dict(row)
    post["reading_time"] = reading_time(post.get("content_md") or "")
    post["tag_list"] = taglist(post.get("tags") or "")
    return post


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


# ---------------------------------------------------------------- 设置


def get_settings() -> dict[str, str]:
    with db.get_conn() as con:
        rows = con.execute("SELECT key, value FROM settings").fetchall()
    return {row["key"]: row["value"] for row in rows}


def get_setting(key: str, default: str = "") -> str:
    with db.get_conn() as con:
        row = con.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def update_settings(values: dict[str, str]) -> None:
    with db.get_conn() as con:
        con.executemany(
            "INSERT INTO settings(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            list(values.items()),
        )


# ---------------------------------------------------------------- 文章：公共


def count_published() -> int:
    with db.get_conn() as con:
        return con.execute(
            "SELECT COUNT(*) AS c FROM posts WHERE status = 'published'"
        ).fetchone()["c"]


def list_published(limit: int, offset: int = 0) -> list[dict]:
    with db.get_conn() as con:
        rows = con.execute(
            "SELECT * FROM posts WHERE status = 'published' "
            "ORDER BY COALESCE(published_at, created_at) DESC, id DESC "
            "LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
    return [_post_dict(row) for row in rows]


def get_post_by_slug(slug: str) -> dict | None:
    with db.get_conn() as con:
        row = con.execute("SELECT * FROM posts WHERE slug = ?", (slug,)).fetchone()
    return _post_dict(row) if row else None


def increment_views(post_id: int) -> None:
    with db.get_conn() as con:
        con.execute("UPDATE posts SET views = views + 1 WHERE id = ?", (post_id,))


def count_posts_by_tag(tag: str) -> int:
    pattern = f"%,{_escape_like(tag)},%"
    with db.get_conn() as con:
        return con.execute(
            "SELECT COUNT(*) AS c FROM posts WHERE status = 'published' "
            "AND (',' || tags || ',') LIKE ? ESCAPE '\\'",
            (pattern,),
        ).fetchone()["c"]


def list_posts_by_tag(tag: str, limit: int, offset: int = 0) -> list[dict]:
    pattern = f"%,{_escape_like(tag)},%"
    with db.get_conn() as con:
        rows = con.execute(
            "SELECT * FROM posts WHERE status = 'published' "
            "AND (',' || tags || ',') LIKE ? ESCAPE '\\' "
            "ORDER BY COALESCE(published_at, created_at) DESC, id DESC "
            "LIMIT ? OFFSET ?",
            (pattern, limit, offset),
        ).fetchall()
    return [_post_dict(row) for row in rows]


def search_posts(query: str, limit: int = 50) -> list[dict]:
    pattern = f"%{_escape_like(query)}%"
    with db.get_conn() as con:
        rows = con.execute(
            "SELECT * FROM posts WHERE status = 'published' AND ("
            "title LIKE ? ESCAPE '\\' OR summary LIKE ? ESCAPE '\\' "
            "OR content_md LIKE ? ESCAPE '\\') "
            "ORDER BY COALESCE(published_at, created_at) DESC, id DESC LIMIT ?",
            (pattern, pattern, pattern, limit),
        ).fetchall()
    return [_post_dict(row) for row in rows]


def all_tags() -> list[dict]:
    with db.get_conn() as con:
        rows = con.execute(
            "SELECT tags FROM posts WHERE status = 'published'"
        ).fetchall()
    counter: Counter[str] = Counter()
    for row in rows:
        for tag in taglist(row["tags"]):
            counter[tag] += 1
    return [
        {"name": name, "count": count}
        for name, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    ]


def archive_groups() -> list[dict]:
    with db.get_conn() as con:
        rows = con.execute(
            "SELECT slug, title, published_at, created_at FROM posts "
            "WHERE status = 'published' "
            "ORDER BY COALESCE(published_at, created_at) DESC, id DESC"
        ).fetchall()
    groups: dict[int, list[dict]] = {}
    for row in rows:
        year = local_year(row["published_at"] or row["created_at"])
        groups.setdefault(year, []).append(
            {
                "slug": row["slug"],
                "title": row["title"],
                "published_at": row["published_at"] or row["created_at"],
            }
        )
    return [{"year": year, "posts": groups[year]} for year in sorted(groups, reverse=True)]


# ---------------------------------------------------------------- 文章：后台


def _unique_slug(con: sqlite3.Connection, base: str, exclude_id: int | None = None) -> str:
    base = base or "post"
    candidate = base
    suffix = 2
    while True:
        row = con.execute("SELECT id FROM posts WHERE slug = ?", (candidate,)).fetchone()
        if row is None or (exclude_id is not None and row["id"] == exclude_id):
            return candidate
        candidate = f"{base}-{suffix}"
        suffix += 1
        if suffix > 1000:
            return f"{base}-{secrets.token_hex(3)}"


def _auto_slug(title: str, slug_input: str) -> str:
    return slugify(slug_input) or slugify(title) or ""


def save_post(
    *,
    post_id: int | None,
    title: str,
    slug: str,
    summary: str,
    tags: str,
    content_md: str,
    status: str,
) -> int | None:
    """新建或更新文章，返回文章 id。"""
    title = (title or "").strip()[:200]
    content_md = content_md or ""
    tags = normalize_tags(tags)
    summary = (summary or "").strip()[:500]
    if not summary:
        summary = excerpt(plain_text(content_md), 150)
    status = status if status in POST_STATUSES else "draft"
    now = utc_now_iso()

    with db.get_conn() as con:
        if post_id:
            row = con.execute("SELECT * FROM posts WHERE id = ?", (post_id,)).fetchone()
            if row is None:
                return None
            base = _auto_slug(title, slug) or f"post-{post_id}"
            new_slug = _unique_slug(con, base, exclude_id=post_id)
            published_at = row["published_at"]
            if status == "published" and not published_at:
                published_at = now
            con.execute(
                "UPDATE posts SET slug = ?, title = ?, summary = ?, content_md = ?, "
                "tags = ?, status = ?, updated_at = ?, published_at = ? WHERE id = ?",
                (new_slug, title, summary, content_md, tags, status, now, published_at, post_id),
            )
            return int(post_id)

        base = _auto_slug(title, slug) or (
            "post-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        )
        new_slug = _unique_slug(con, base)
        cur = con.execute(
            "INSERT INTO posts(slug, title, summary, content_md, tags, status, views,"
            " created_at, updated_at, published_at) VALUES(?, ?, ?, ?, ?, ?, 0, ?, ?, ?)",
            (
                new_slug,
                title,
                summary,
                content_md,
                tags,
                status,
                now,
                now,
                now if status == "published" else None,
            ),
        )
        return int(cur.lastrowid)


def get_post_by_id(post_id: int) -> dict | None:
    with db.get_conn() as con:
        row = con.execute("SELECT * FROM posts WHERE id = ?", (post_id,)).fetchone()
    return _post_dict(row) if row else None


def count_posts(status: str | None = None) -> int:
    with db.get_conn() as con:
        if status in POST_STATUSES:
            return con.execute(
                "SELECT COUNT(*) AS c FROM posts WHERE status = ?", (status,)
            ).fetchone()["c"]
        return con.execute("SELECT COUNT(*) AS c FROM posts").fetchone()["c"]


def list_posts(limit: int = 20, offset: int = 0, status: str | None = None) -> list[dict]:
    with db.get_conn() as con:
        if status in POST_STATUSES:
            rows = con.execute(
                "SELECT * FROM posts WHERE status = ? "
                "ORDER BY updated_at DESC, id DESC LIMIT ? OFFSET ?",
                (status, limit, offset),
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT * FROM posts ORDER BY updated_at DESC, id DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
    return [_post_dict(row) for row in rows]


def post_counts() -> dict[str, int]:
    with db.get_conn() as con:
        total = con.execute("SELECT COUNT(*) AS c FROM posts").fetchone()["c"]
        published = con.execute(
            "SELECT COUNT(*) AS c FROM posts WHERE status = 'published'"
        ).fetchone()["c"]
    return {"all": total, "published": published, "drafts": total - published}


def recent_posts(limit: int = 10) -> list[dict]:
    with db.get_conn() as con:
        rows = con.execute(
            "SELECT * FROM posts ORDER BY updated_at DESC, id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [_post_dict(row) for row in rows]


def delete_post(post_id: int) -> bool:
    with db.get_conn() as con:
        cur = con.execute("DELETE FROM posts WHERE id = ?", (post_id,))
        return cur.rowcount > 0


def toggle_post_status(post_id: int) -> str | None:
    with db.get_conn() as con:
        row = con.execute("SELECT * FROM posts WHERE id = ?", (post_id,)).fetchone()
        if row is None:
            return None
        new_status = "draft" if row["status"] == "published" else "published"
        now = utc_now_iso()
        published_at = row["published_at"]
        if new_status == "published" and not published_at:
            published_at = now
        con.execute(
            "UPDATE posts SET status = ?, published_at = ?, updated_at = ? WHERE id = ?",
            (new_status, published_at, now, post_id),
        )
        return new_status


# ---------------------------------------------------------------- 评论


def create_comment(
    post_id: int, author: str, email: str, content: str, ip: str = ""
) -> int:
    with db.get_conn() as con:
        cur = con.execute(
            "INSERT INTO comments(post_id, author, email, content, status, created_at, ip)"
            " VALUES(?, ?, ?, ?, 'pending', ?, ?)",
            (post_id, author, email, content, utc_now_iso(), ip),
        )
        return int(cur.lastrowid)


def list_approved_comments(post_id: int) -> list[dict]:
    with db.get_conn() as con:
        rows = con.execute(
            "SELECT id, author, content, created_at FROM comments "
            "WHERE post_id = ? AND status = 'approved' ORDER BY created_at ASC, id ASC",
            (post_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def count_approved_comments(post_id: int) -> int:
    with db.get_conn() as con:
        return con.execute(
            "SELECT COUNT(*) AS c FROM comments WHERE post_id = ? AND status = 'approved'",
            (post_id,),
        ).fetchone()["c"]


def list_comments(status: str | None = None, limit: int = 20, offset: int = 0) -> list[dict]:
    sql = (
        "SELECT c.*, p.title AS post_title, p.slug AS post_slug "
        "FROM comments c JOIN posts p ON p.id = c.post_id "
    )
    params: tuple = ()
    if status in COMMENT_STATUSES:
        sql += "WHERE c.status = ? "
        params = (status,)
    sql += "ORDER BY c.created_at DESC, c.id DESC LIMIT ? OFFSET ?"
    with db.get_conn() as con:
        rows = con.execute(sql, params + (limit, offset)).fetchall()
    return [dict(row) for row in rows]


def count_comments(status: str | None = None) -> int:
    with db.get_conn() as con:
        if status in COMMENT_STATUSES:
            return con.execute(
                "SELECT COUNT(*) AS c FROM comments WHERE status = ?", (status,)
            ).fetchone()["c"]
        return con.execute("SELECT COUNT(*) AS c FROM comments").fetchone()["c"]


def comment_counts() -> dict[str, int]:
    with db.get_conn() as con:
        pending = con.execute(
            "SELECT COUNT(*) AS c FROM comments WHERE status = 'pending'"
        ).fetchone()["c"]
        approved = con.execute(
            "SELECT COUNT(*) AS c FROM comments WHERE status = 'approved'"
        ).fetchone()["c"]
    return {"pending": pending, "approved": approved}


def set_comment_status(comment_id: int, status: str) -> bool:
    if status not in COMMENT_STATUSES:
        return False
    with db.get_conn() as con:
        cur = con.execute(
            "UPDATE comments SET status = ? WHERE id = ?", (status, comment_id)
        )
        return cur.rowcount > 0


def delete_comment(comment_id: int) -> bool:
    with db.get_conn() as con:
        cur = con.execute("DELETE FROM comments WHERE id = ?", (comment_id,))
        return cur.rowcount > 0


def recent_comments(limit: int = 5) -> list[dict]:
    with db.get_conn() as con:
        rows = con.execute(
            "SELECT c.*, p.title AS post_title, p.slug AS post_slug "
            "FROM comments c JOIN posts p ON p.id = c.post_id "
            "ORDER BY c.created_at DESC, c.id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


# ---------------------------------------------------------------- 统计 / 用户


def dashboard_stats() -> dict[str, int]:
    with db.get_conn() as con:
        published = con.execute(
            "SELECT COUNT(*) AS c FROM posts WHERE status = 'published'"
        ).fetchone()["c"]
        drafts = con.execute(
            "SELECT COUNT(*) AS c FROM posts WHERE status = 'draft'"
        ).fetchone()["c"]
        views = con.execute("SELECT COALESCE(SUM(views), 0) AS v FROM posts").fetchone()["v"]
        comments_pending = con.execute(
            "SELECT COUNT(*) AS c FROM comments WHERE status = 'pending'"
        ).fetchone()["c"]
        comments_total = con.execute("SELECT COUNT(*) AS c FROM comments").fetchone()["c"]
    return {
        "published": published,
        "drafts": drafts,
        "views": views,
        "comments_pending": comments_pending,
        "comments_total": comments_total,
    }


def get_user_by_username(username: str) -> dict | None:
    with db.get_conn() as con:
        row = con.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    return dict(row) if row else None


def get_user_by_id(user_id: int) -> dict | None:
    with db.get_conn() as con:
        row = con.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return dict(row) if row else None


def update_user_password(user_id: int, password_hash: str) -> bool:
    with db.get_conn() as con:
        cur = con.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?", (password_hash, user_id)
        )
        return cur.rowcount > 0
