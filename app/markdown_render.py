"""Markdown 渲染。

文章内容只来自受信任的管理员（单用户博客），因此允许内嵌 HTML；
如果需要多作者或开放投稿，请在渲染后追加 HTML 白名单清洗。
"""

from __future__ import annotations

import re

import markdown
from markupsafe import Markup

EXTENSIONS = ["fenced_code", "tables", "sane_lists", "nl2br", "toc"]

# 匹配 <img ...>（属性值里允许出现 ">"，避免截断标签；不跨越到下一个标签）。
_IMG_TAG_RE = re.compile(r"""<img\b(?:[^<>"']|"[^"]*"|'[^']*')*>""", re.IGNORECASE)
_LOADING_ATTR_RE = re.compile(r"\s+loading\s*=", re.IGNORECASE)
_DECODING_ATTR_RE = re.compile(r"\s+decoding\s*=", re.IGNORECASE)


def _add_lazy_images(html_text: str) -> str:
    """给渲染后的 <img> 补充 loading="lazy" / decoding="async"。

    已存在的同名属性（大小写不敏感）不会重复添加；`<img>` 与 `<img />` 均可处理。
    """
    if "<img" not in html_text.lower():
        return html_text

    def _repl(match: re.Match) -> str:
        tag = match.group(0)
        additions = []
        if not _LOADING_ATTR_RE.search(tag):
            additions.append('loading="lazy"')
        if not _DECODING_ATTR_RE.search(tag):
            additions.append('decoding="async"')
        if not additions:
            return tag
        if tag.endswith("/>"):
            return f"{tag[:-2].rstrip()} {' '.join(additions)} />"
        return f"{tag[:-1].rstrip()} {' '.join(additions)}>"

    return _IMG_TAG_RE.sub(_repl, html_text)


def render_markdown(text: str) -> Markup:
    if not text:
        return Markup("")
    converter = markdown.Markdown(extensions=EXTENSIONS, output_format="html5")
    # 文章内容仅来自受信任的管理员（见模块 docstring），此处 Markup 为有意为之。
    rendered = _add_lazy_images(converter.convert(text))
    return Markup(rendered)  # nosec B704
