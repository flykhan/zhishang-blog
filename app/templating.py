"""Jinja2 环境、过滤器与模板渲染辅助函数。"""

from __future__ import annotations

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
    excerpt,
    format_date,
    format_footer,
    reading_time,
    taglist,
)

BASE_DIR = Path(__file__).resolve().parent

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
