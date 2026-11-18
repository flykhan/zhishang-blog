"""Jinja2 环境、过滤器与模板渲染辅助函数。"""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from jinja2 import StrictUndefined

from . import repo
from .config import settings
from .markdown_render import render_markdown
from .utils import (
    build_flash,
    clean_summary,
    excerpt,
    format_date,
    format_footer,
    reading_time,
    taglist,
)

BASE_DIR = Path(__file__).resolve().parent

# 静态资源版本号：进程启动（容器重启）时变化，配合长缓存让 style.css / app.js 自动失效。
ASSET_VERSION = str(int(time.time()))


def jsonld_dumps(data: dict) -> str:
    """把 JSON-LD 数据序列化为可安全内嵌到 <script> 的字符串。

    转义 `</` 为 `<\\/`，避免正文/标题里出现 `</script>` 提前闭合脚本块；
    该转义仍是合法 JSON，解析后字符串内容不变。
    """
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return text.replace("</", "<\\/")


def site_jsonld(site: dict) -> str:
    """生成站点级 WebSite 结构化数据（JSON 字符串）。"""
    return jsonld_dumps(
        {
            "@context": "https://schema.org",
            "@type": "WebSite",
            "name": site.get("site_title", ""),
            "url": settings.site_url_base,
            "description": site.get("site_description", ""),
            "inLanguage": "zh-CN",
        }
    )


templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
templates.env.undefined = StrictUndefined
templates.env.trim_blocks = True
templates.env.lstrip_blocks = True
templates.env.filters.update(
    {
        "date": format_date,
        "md": render_markdown,
        "taglist": taglist,
        "excerpt": excerpt,
        "reading_time": reading_time,
        "footer": format_footer,
        "clean_summary": clean_summary,
    }
)


def base_context(request: Request) -> dict:
    session_user = getattr(request.state, "user", None)
    site = repo.get_settings()
    return {
        "request": request,
        "site": site,
        "user": session_user,
        "csrf": getattr(request.state, "csrf", "") or "",
        "flash": build_flash(
            request.query_params.get("ok"), request.query_params.get("err")
        ),
        "now_year": datetime.now(settings.timezone).year,
        "site_url": settings.site_url_base,
        "asset_version": ASSET_VERSION,
        "site_jsonld": site_jsonld(site),
    }


def render(request: Request, template_name: str, status_code: int = 200, **context) -> HTMLResponse:
    ctx = base_context(request)
    ctx.update(context)
    return templates.TemplateResponse(
        request=request, name=template_name, context=ctx, status_code=status_code
    )


def render_admin(
    request: Request, template_name: str, status_code: int = 200, **context
) -> HTMLResponse:
    ctx = base_context(request)
    ctx["pending_comments"] = repo.count_comments("pending")
    ctx.update(context)
    return templates.TemplateResponse(
        request=request, name=template_name, context=ctx, status_code=status_code
    )
