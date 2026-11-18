"""FastAPI 应用入口：中间件、静态资源、路由与错误处理。"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import auth, db
from .config import settings
from .routes_admin import router as admin_router
from .routes_public import router as public_router
from .templating import render

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("paper")

BASE_DIR = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    if settings.admin_password == "admin123":
        logger.warning(
            "当前管理员仍是默认密码 admin123，请登录后立刻在「设置」中修改。"
        )
    logger.info("博客已就绪：数据库 %s", settings.db_path)
    yield


app = FastAPI(
    title="纸上",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


@app.middleware("http")
async def attach_context(request: Request, call_next):
    session = auth.load_session(request)
    request.state.user = (
        {"id": session["uid"], "username": session["u"]} if session else None
    )
    request.state.csrf = session.get("csrf", "") if session else ""

    response = await call_next(request)

    headers = response.headers
    headers.setdefault("X-Content-Type-Options", "nosniff")
    headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    headers.setdefault(
        "Permissions-Policy", "geolocation=(), microphone=(), camera=()"
    )
    headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; "
        "img-src 'self' data: https:; "
        "style-src 'self' 'unsafe-inline'; "
        "script-src 'self' 'unsafe-inline'; "
        "form-action 'self'; "
        "base-uri 'self'; "
        "object-src 'none'",
    )
    return response


app.include_router(public_router)
app.include_router(admin_router)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 404:
        return render(request, "404.html", page_title="页面不存在", status_code=404)
    if request.url.path.startswith("/admin"):
        return PlainTextResponse(str(exc.detail), status_code=exc.status_code)
    return PlainTextResponse(str(exc.detail), status_code=exc.status_code)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("未处理的异常：%s %s", request.method, request.url.path)
    return PlainTextResponse("服务器开小差了，请稍后再试。", status_code=500)
