"""Markdown 渲染。

文章内容只来自受信任的管理员（单用户博客），因此允许内嵌 HTML；
如果需要多作者或开放投稿，请在渲染后追加 HTML 白名单清洗。
"""

from __future__ import annotations

import markdown
from markupsafe import Markup

EXTENSIONS = ["fenced_code", "tables", "sane_lists", "nl2br", "toc"]


def render_markdown(text: str) -> Markup:
    if not text:
        return Markup("")
    converter = markdown.Markdown(extensions=EXTENSIONS, output_format="html5")
    # 文章内容仅来自受信任的管理员（见模块 docstring），此处 Markup 为有意为之。
    return Markup(converter.convert(text))  # nosec B704
