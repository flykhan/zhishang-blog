"""通用工具：时间、摘要、标签、Markdown 纯文本、flash 文案。"""

from __future__ import annotations

import math
import re
import unicodedata
from datetime import datetime, timezone

from .config import settings

CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
WORD_RE = re.compile(r"[A-Za-z0-9_]+")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_iso(value) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def format_date(value, fmt: str = "%Y年%m月%d日") -> str:
    """Jinja 过滤器：把 ISO 时间串按站点时区格式化。"""
    dt = parse_iso(value)
    if dt is None:
        return "" if not value else str(value)
    return dt.astimezone(settings.timezone).strftime(fmt)


def local_year(value) -> int:
    dt = parse_iso(value)
    if dt is None:
        return 0
    return dt.astimezone(settings.timezone).year


def plain_text(markdown_text: str) -> str:
    """把 Markdown 粗略转成纯文本（用于摘要与字数统计）。"""
    if not markdown_text:
        return ""
    text = re.sub(r"```.*?```", " ", markdown_text, flags=re.S)
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"^\s{0,3}#{1,6}\s*", "", text, flags=re.M)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[*_~]+", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def excerpt(text: str, length: int = 160) -> str:
    """纯文本截断；传入的 markdown 会先被转成纯文本。"""
    clean = plain_text(text)
    if len(clean) <= length:
        return clean
    return clean[:length].rstrip() + "…"


def reading_time(markdown_text: str) -> int:
    """估算阅读时长（分钟）：中文 350 字/分钟，英文 200 词/分钟。"""
    if not markdown_text:
        return 1
    cjk_chars = len(CJK_RE.findall(markdown_text))
    latin_words = len(WORD_RE.findall(CJK_RE.sub(" ", markdown_text)))
    minutes = math.ceil(cjk_chars / 350 + latin_words / 200)
    return max(1, minutes)


def slugify(value) -> str:
    if not value:
        return ""
    text = unicodedata.normalize("NFKD", str(value))
    text = text.encode("ascii", "ignore").decode("ascii").lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-{2,}", "-", text).strip("-")
    return text[:80].strip("-")


def normalize_tags(raw) -> str:
    """逗号（含中文逗号/顿号）分隔 → 去空、去重、限长。"""
    if not raw:
        return ""
    parts = re.split(r"[,，、]", str(raw))
    seen: list[str] = []
    lowered: set[str] = set()
    for part in parts:
        tag = part.strip()[:30]
        if not tag:
            continue
        key = tag.lower()
        if key in lowered:
            continue
        lowered.add(key)
        seen.append(tag)
        if len(seen) >= 10:
            break
    return ",".join(seen)


def taglist(raw) -> list[str]:
    if not raw:
        return []
    return [tag.strip() for tag in str(raw).split(",") if tag.strip()]


def format_footer(text: str) -> str:
    year = datetime.now(settings.timezone).year
    return (text or "").replace("{year}", str(year))


def comment_email_valid(email: str) -> bool:
    return bool(EMAIL_RE.match(email))


OK_MESSAGES = {
    "saved": "文章已保存",
    "deleted": "文章已删除",
    "published": "文章已发布",
    "unpublished": "已转为草稿",
    "approved": "评论已通过，现已公开",
    "comment_deleted": "评论已删除",
    "settings_saved": "设置已保存",
    "password_changed": "密码已修改，下次登录请使用新密码",
    "login": "欢迎回来",
    "logged_out": "已退出登录",
    "comment": "评论已提交，审核通过后显示",
}

ERR_MESSAGES = {
    "notfound": "内容不存在或已被删除",
    "invalid": "表单填写有误，请检查后重试",
    "wrong_password": "当前密码不正确",
    "rate_limited": "操作过于频繁，请稍后再试",
    "comment_closed": "该文章已关闭评论",
    "comment_invalid": "评论内容不合法（昵称 1–60 字，内容 2–2000 字）",
    "forbidden": "没有权限执行该操作",
    "bad_request": "请求无效",
    "empty": "请填写完整信息",
}


def build_flash(ok_code, err_code) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    if ok_code and ok_code in OK_MESSAGES:
        messages.append({"kind": "ok", "text": OK_MESSAGES[ok_code]})
    if err_code and err_code in ERR_MESSAGES:
        messages.append({"kind": "err", "text": ERR_MESSAGES[err_code]})
    return messages
