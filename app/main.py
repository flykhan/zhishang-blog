"""FastAPI 应用入口：中间件、静态资源、路由与错误处理。"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import auth, db, repo
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

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "SAMEORIGIN",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
    "Content-Security-Policy": (
        "default-src 'self'; "
        "img-src 'self' data: https:; "
        "style-src 'self' 'unsafe-inline'; "
        "script-src 'self' 'unsafe-inline'; "
        "form-action 'self'; "
        "base-uri 'self'; "
        "object-src 'none'"
    ),
}


def apply_security_headers(response) -> None:
    for key, value in SECURITY_HEADERS.items():
        response.headers.setdefault(key, value)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    # 默认占位密码只用于启动告警提示，不是真实凭据。
    if settings.admin_password == "admin123":  # nosec B105
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
    path = request.url.path

    # 1) 请求体大小限制：阻挡未认证的巨型表单（防内存 / worker DoS）。
    if request.method in {"POST", "PUT", "PATCH"}:
        raw_length = request.headers.get("content-length", "")
        if raw_length.isdigit() and int(raw_length) > settings.max_body_bytes:
            response = PlainTextResponse("请求体过大", status_code=413)
            apply_security_headers(response)
            return response

    # 2) 静态资源不需要会话校验，避免每个 CSS/JS 请求都查询数据库。
    if path.startswith("/static/"):
        request.state.user = None
        request.state.csrf = ""
        response = await call_next(request)
        apply_security_headers(response)
        return response

    # 3) 会话校验：签名有效 + 用户存在 + 会话版本匹配（改密后旧会话立即失效）。
    session = auth.load_session(request)
    user = None
    stale_session = False
    if session:
        db_user = repo.get_user_by_id(int(session.get("uid", 0)))
        if db_user is None or int(session.get("sv", 0)) != int(
            db_user["session_version"]
        ):
            stale_session = True
        else:
            user = {
                "id": db_user["id"],
                "username": db_user["username"],
                "must_change_password": bool(db_user["must_change_password"]),
            }
    request.state.user = user
    request.state.csrf = str(session.get("csrf", "")) if (session and user) else ""

    response = await call_next(request)

    if stale_session:
        auth.clear_session_cookie(response)

    apply_security_headers(response)

    # 4) 后台页面禁止缓存：避免共享代理 / 浏览器后退泄露草稿、评论邮箱、CSRF token。
    if path == "/admin" or path.startswith("/admin/"):
        response.headers["Cache-Control"] = (
            "no-store, no-cache, must-revalidate, private"
        )
        response.headers["Pragma"] = "no-cache"
        response.headers["Vary"] = "Cookie"

    return response


app.include_router(public_router)
app.include_router(admin_router)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 404:
        response = render(request, "404.html", page_title="页面不存在", status_code=404)
    else:
        response = PlainTextResponse(str(exc.detail), status_code=exc.status_code)
    apply_security_headers(response)
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("未处理的异常：%s %s", request.method, request.url.path)
    response = PlainTextResponse("服务器开小差了，请稍后再试。", status_code=500)
    apply_security_headers(response)
    return response
