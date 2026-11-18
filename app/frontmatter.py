"""Markdown frontmatter 解析与导入字段归一化。

支持常见的 Jekyll / Hugo / Hexo / Obsidian 风格 YAML frontmatter：
    ---
    title: 你好
    date: 2024-04-17 11:52:50
    tags: [随笔, 技术]
    slug: hello
    summary: 摘要
    status: published
    ---
正文……

兼容缺失 frontmatter、BOM、CRLF、各种日期格式以及时间戳。
解析失败通过 FrontmatterError 报出，由导入接口转成「该文件失败」的结果。
"""

from __future__ import annotations

import re
from datetime import date, datetime, timezone

import yaml

from .config import settings
from .utils import slugify

FRONTMATTER_START_RE = re.compile(r"^---[ \t]*\r?\n")
FRONTMATTER_RE = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.S)
H1_RE = re.compile(r"^#[ \t]+(.+?)[ \t]*$", re.M)

DATE_KEYS = (
    "date",
    "published_at",
    "publishedAt",
    "publishTime",
    "created_at",
    "createdAt",
    "created",
)
TAG_KEYS = ("tags", "tag", "categories", "category")
SUMMARY_KEYS = ("summary", "excerpt", "description", "lede", "abstract")
SLUG_KEYS = ("slug", "permalink", "url")
_STATUS_WORDS = {
    "draft": "draft",
    "草稿": "draft",
    "published": "published",
    "publish": "published",
    "public": "published",
    "公开": "published",
    "发布": "published",
}
_DATE_FORMATS = (
    "%Y-%m-%d %H:%M:%S.%f",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d",
    "%Y/%m/%d %H:%M:%S",
    "%Y/%m/%d",
    "%Y年%m月%d日",
)


class FrontmatterError(ValueError):
    """frontmatter 无法解析。"""


def split_frontmatter(text: str) -> tuple[dict, str]:
    """拆分 YAML frontmatter 与正文，返回 (元数据, 正文)。"""
    if text.startswith("\ufeff"):
        text = text[1:]
    if not FRONTMATTER_START_RE.match(text):
        return {}, text

    match = FRONTMATTER_RE.match(text)
    if match is None:
        raise FrontmatterError("frontmatter 缺少结束的 --- 分隔线")
    raw = match.group(1)
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise FrontmatterError("frontmatter YAML 解析失败") from exc
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise FrontmatterError("frontmatter 必须是键值对")
    return data, text[match.end():]


def _as_bool(value) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        word = value.strip().lower()
        if word in {"true", "yes", "y", "on", "1"}:
            return True
        if word in {"false", "no", "n", "off", "0"}:
            return False
    return None


def normalize_date(value) -> str | None:
    """把 frontmatter 里的日期归一化为 UTC ISO-8601（秒级）。"""
    if value is None or isinstance(value, bool):
        return None

    parsed: datetime | None = None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime(value.year, value.month, value.day)
    elif isinstance(value, (int, float)):
        timestamp = float(value)
        if timestamp > 1e12:  # 毫秒时间戳
            timestamp /= 1000.0
        try:
            return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat(
                timespec="seconds"
            )
        except (OverflowError, OSError, ValueError):
            return None
    elif isinstance(value, str):
        text = value.strip().strip("\"'")
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            for fmt in _DATE_FORMATS:
                try:
                    parsed = datetime.strptime(text, fmt)
                    break
                except ValueError:
                    continue
        if parsed is None:
            return None
    else:
        return None

    if parsed.tzinfo is None:
        try:
            parsed = parsed.replace(tzinfo=settings.timezone)
        except Exception:  # 极端情况下时区不可用时退回 UTC
            parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat(timespec="seconds")


def extract_published_at(data: dict) -> str | None:
    for key in DATE_KEYS:
        if key in data:
            normalized = normalize_date(data[key])
            if normalized:
                return normalized
    return None


def _flatten_tags(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [part.strip() for part in re.split(r"[,，、]", value) if part.strip()]
    if isinstance(value, dict):
        for key in ("name", "displayName", "title"):
            item = value.get(key)
            if isinstance(item, str) and item.strip():
                return [item.strip()]
        return []
    if isinstance(value, (list, tuple, set)):
        collected: list[str] = []
        for item in value:
            collected.extend(_flatten_tags(item))
        return collected
    return []


def extract_tags(data: dict) -> list[str]:
    collected: list[str] = []
    for key in TAG_KEYS:
        collected.extend(_flatten_tags(data.get(key)))
    return collected


def extract_summary(data: dict) -> str:
    for key in SUMMARY_KEYS:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()[:500]
    return ""


def extract_slug(data: dict) -> str:
    for key in SLUG_KEYS:
        value = data.get(key)
        if not isinstance(value, str):
            continue
        candidate = value.strip()
        if not candidate:
            continue
        # 兼容 /archives/foo、/post/foo 这类完整路径
        candidate = candidate.rstrip("/").rsplit("/", 1)[-1]
        slug = slugify(candidate)
        if slug:
            return slug
    return ""


def clean_title(value) -> str:
    text = str(value or "").strip().strip("\"'“”‘’")
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\.(md|markdown|mdown|mkd)$", "", text, flags=re.I).strip()
    return text[:200]


def extract_title(data: dict, body: str, filename_stem: str = "") -> str:
    for key in ("title", "name"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return clean_title(value)
    heading = H1_RE.search(body)
    if heading:
        return clean_title(heading.group(1))
    return clean_title(re.sub(r"[-_]+", " ", filename_stem))


def resolve_status(data: dict, default: str = "published") -> str:
    draft = _as_bool(data.get("draft"))
    if draft is not None:
        return "draft" if draft else "published"
    for key in ("status", "published", "publish"):
        value = data.get(key)
        if isinstance(value, bool):
            return "published" if value else "draft"
        if isinstance(value, str):
            word = _STATUS_WORDS.get(value.strip().lower())
            if word:
                return word
    return "published" if default == "published" else "draft"
