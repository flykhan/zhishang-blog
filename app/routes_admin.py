"""后台路由：登录、仪表盘、文章 CRUD、评论审核、站点设置、Markdown 预览与导入。"""

from __future__ import annotations

import hmac
import logging
import secrets
import math
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlencode

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    RedirectResponse,
)

from . import auth, frontmatter, repo
from .config import settings
from .markdown_render import render_markdown
from .templating import render_admin
from .utils import normalize_tags, slugify

logger = logging.getLogger("paper.import")

router = APIRouter()


# ---------------------------------------------------------------- 辅助


def _current_user(request: Request) -> dict | None:
    return getattr(request.state, "user", None)


def _login_redirect() -> RedirectResponse:
    return RedirectResponse("/admin/login", status_code=303)


def _csrf_ok(request: Request, form) -> bool:
    expected = str(getattr(request.state, "csrf", "") or "")
    provided = str(form.get("csrf_token") or "")
    if not expected or not provided:
        return False
    return hmac.compare_digest(
        provided.encode("utf-8", "backslashreplace"),
        expected.encode("utf-8", "backslashreplace"),
    )


def _ensure_valid_id(value: int) -> None:
    if not repo.valid_id(value):
        raise HTTPException(status_code=404)


def _field(form, name: str, limit: int = 10000) -> str:
    return str(form.get(name) or "").strip()[:limit]


def _admin_pagination(
    page: int, total_pages: int, total_items: int, base_path: str, status_filter: str
) -> dict:
    def page_url(number: int) -> str:
        return f"{base_path}?{urlencode({'status': status_filter, 'page': number})}"

    return {
        "page": page,
        "total_pages": total_pages,
        "total_items": total_items,
        "prev_url": page_url(page - 1) if page > 1 else None,
        "next_url": page_url(page + 1) if page < total_pages else None,
    }


def _int_param(request: Request, name: str, default: int) -> int:
    try:
        return int(request.query_params.get(name, default))
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------- 登录 / 退出


@router.get("/admin/login", response_class=HTMLResponse)
def login_page(request: Request):
    if _current_user(request):
        return RedirectResponse("/admin", status_code=303)
    token = request.cookies.get(auth.LOGIN_CSRF_COOKIE) or auth.new_login_csrf()
    response = render_admin(
        request,
        "admin/login.html",
        csrf=token,
        username="",
        error=None,
        page_title="登录",
    )
    response.set_cookie(
        auth.LOGIN_CSRF_COOKIE,
        token,
        max_age=1800,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        path="/admin",
    )
    return response


@router.post("/admin/login")
async def login_submit(request: Request):
    if _current_user(request):
        return RedirectResponse("/admin", status_code=303)

    form = await request.form()
    username = _field(form, "username", 80)
    password = str(form.get("password") or "")
    provided = str(form.get("csrf_token") or "")
    cookie_token = request.cookies.get(auth.LOGIN_CSRF_COOKIE) or ""

    if (
        not cookie_token
        or not provided
        or not hmac.compare_digest(
            provided.encode("utf-8", "backslashreplace"),
            cookie_token.encode("utf-8", "backslashreplace"),
        )
    ):
        return PlainTextResponse("表单已过期，请刷新页面后重试。", status_code=400)

    ip = auth.client_ip(request)
    if not auth.login_allowed(ip):
        response = render_admin(
            request,
            "admin/login.html",
            csrf=cookie_token,
            username=username,
            error="尝试次数过多，请 10 分钟后再试。",
            page_title="登录",
            status_code=429,
        )
        response.headers["Retry-After"] = "600"
        return response

    user = repo.get_user_by_username(username)
    if user is None or not auth.verify_password(password, user["password_hash"]):
        auth.record_login_failure(ip)
        return render_admin(
            request,
            "admin/login.html",
            csrf=cookie_token,
            username=username,
            error="用户名或密码不正确。",
            page_title="登录",
            status_code=401,
        )

    auth.clear_login_failures(ip)
    token = auth.create_session(
        user["id"], user["username"], int(user.get("session_version") or 0)
    )
    response = RedirectResponse("/admin?ok=login", status_code=303)
    auth.set_session_cookie(response, token)
    response.delete_cookie(auth.LOGIN_CSRF_COOKIE, path="/admin")
    return response


@router.post("/admin/logout")
async def logout(request: Request):
    if not _current_user(request):
        return _login_redirect()
    form = await request.form()
    if not _csrf_ok(request, form):
        return PlainTextResponse("CSRF 校验失败", status_code=400)
    response = RedirectResponse("/admin/login?ok=logged_out", status_code=303)
    auth.clear_session_cookie(response)
    return response


# ---------------------------------------------------------------- 仪表盘


@router.get("/admin", response_class=HTMLResponse)
def dashboard(request: Request):
    if not _current_user(request):
        return _login_redirect()
    return render_admin(
        request,
        "admin/dashboard.html",
        active_nav="dashboard",
        stats=repo.dashboard_stats(),
        posts=repo.recent_posts(10),
        recent_comments=repo.recent_comments(5),
        page_title="仪表盘",
    )


# ---------------------------------------------------------------- 文章


@router.get("/admin/posts", response_class=HTMLResponse)
def posts_page(request: Request):
    if not _current_user(request):
        return _login_redirect()
    status_filter = request.query_params.get("status", "all")
    if status_filter not in ("all", "published", "draft"):
        status_filter = "all"
    page = _int_param(request, "page", 1)
    per_page = 12
    filter_status = None if status_filter == "all" else status_filter
    total = repo.count_posts(filter_status)
    total_pages = max(1, math.ceil(total / per_page))
    page = min(max(1, page), total_pages)
    posts = repo.list_posts(per_page, (page - 1) * per_page, filter_status)
    return render_admin(
        request,
        "admin/posts.html",
        active_nav="posts",
        posts=posts,
        status_filter=status_filter,
        counts=repo.post_counts(),
        pagination=_admin_pagination(
            page, total_pages, total, "/admin/posts", status_filter
        ),
        page_title="文章",
    )


@router.get("/admin/posts/new", response_class=HTMLResponse)
def new_post_page(request: Request):
    if not _current_user(request):
        return _login_redirect()
    return render_admin(
        request,
        "admin/editor.html",
        active_nav="new",
        post=None,
        error=None,
        page_title="写文章",
    )


@router.get("/admin/posts/{post_id:int}/edit", response_class=HTMLResponse)
def edit_post_page(request: Request, post_id: int):
    if not _current_user(request):
        return _login_redirect()
    _ensure_valid_id(post_id)
    post = repo.get_post_by_id(post_id)
    if post is None:
        raise HTTPException(status_code=404)
    return render_admin(
        request,
        "admin/editor.html",
        active_nav="posts",
        post=post,
        error=None,
        page_title=f"编辑：{post['title']}",
    )


@router.post("/admin/posts/save")
async def save_post(request: Request):
    if not _current_user(request):
        return _login_redirect()
    form = await request.form()
    if not _csrf_ok(request, form):
        return PlainTextResponse("CSRF 校验失败", status_code=400)

    try:
        post_id = int(str(form.get("id") or "0"))
    except ValueError:
        post_id = 0
    title = _field(form, "title", 200)
    slug_input = _field(form, "slug", 120)
    summary = _field(form, "summary", 500)
    tags = _field(form, "tags", 200)
    content_md = str(form.get("content_md") or "")[:200000]
    status = str(form.get("status") or "draft")
    if status not in ("draft", "published"):
        status = "draft"

    if not title:
        existing = repo.get_post_by_id(post_id) if post_id else None
        post = dict(existing) if existing else {
            "id": post_id or 0,
            "slug": "",
            "title": "",
            "summary": "",
            "tags": "",
            "content_md": "",
            "status": "draft",
        }
        post.update(
            {
                "title": title,
                "slug": slug_input,
                "summary": summary,
                "tags": tags,
                "content_md": content_md,
                "status": status,
            }
        )
        return render_admin(
            request,
            "admin/editor.html",
            active_nav="new" if not post_id else "posts",
            post=post,
            error="标题不能为空。",
            page_title="写文章",
            status_code=400,
        )

    saved_id = repo.save_post(
        post_id=post_id or None,
        title=title,
        slug=slug_input,
        summary=summary,
        tags=tags,
        content_md=content_md,
        status=status,
    )
    if saved_id is None:
        raise HTTPException(status_code=404)
    return RedirectResponse(f"/admin/posts/{saved_id}/edit?ok=saved", status_code=303)


@router.post("/admin/posts/{post_id:int}/delete")
async def delete_post(request: Request, post_id: int):
    if not _current_user(request):
        return _login_redirect()
    form = await request.form()
    if not _csrf_ok(request, form):
        return PlainTextResponse("CSRF 校验失败", status_code=400)
    _ensure_valid_id(post_id)
    if not repo.delete_post(post_id):
        raise HTTPException(status_code=404)
    return RedirectResponse("/admin/posts?ok=deleted", status_code=303)


@router.post("/admin/posts/{post_id:int}/toggle")
async def toggle_post(request: Request, post_id: int):
    if not _current_user(request):
        return _login_redirect()
    form = await request.form()
    if not _csrf_ok(request, form):
        return PlainTextResponse("CSRF 校验失败", status_code=400)
    _ensure_valid_id(post_id)
    new_status = repo.toggle_post_status(post_id)
    if new_status is None:
        raise HTTPException(status_code=404)
    code = "published" if new_status == "published" else "unpublished"
    return RedirectResponse(f"/admin/posts?ok={code}", status_code=303)


# ---------------------------------------------------------------- 评论


@router.get("/admin/comments", response_class=HTMLResponse)
def comments_page(request: Request):
    if not _current_user(request):
        return _login_redirect()
    status_filter = request.query_params.get("status", "pending")
    if status_filter not in ("pending", "approved", "all"):
        status_filter = "pending"
    page = _int_param(request, "page", 1)
    per_page = 20
    filter_status = None if status_filter == "all" else status_filter
    total = repo.count_comments(filter_status)
    total_pages = max(1, math.ceil(total / per_page))
    page = min(max(1, page), total_pages)
    comments = repo.list_comments(filter_status, per_page, (page - 1) * per_page)
    return render_admin(
        request,
        "admin/comments.html",
        active_nav="comments",
        comments=comments,
        status_filter=status_filter,
        counts=repo.comment_counts(),
        pagination=_admin_pagination(
            page, total_pages, total, "/admin/comments", status_filter
        ),
        page_title="评论",
    )


@router.post("/admin/comments/{comment_id:int}/approve")
async def approve_comment(request: Request, comment_id: int):
    if not _current_user(request):
        return _login_redirect()
    form = await request.form()
    if not _csrf_ok(request, form):
        return PlainTextResponse("CSRF 校验失败", status_code=400)
    _ensure_valid_id(comment_id)
    if not repo.set_comment_status(comment_id, "approved"):
        raise HTTPException(status_code=404)
    return RedirectResponse("/admin/comments?status=pending&ok=approved", status_code=303)


@router.post("/admin/comments/{comment_id:int}/delete")
async def delete_comment(request: Request, comment_id: int):
    if not _current_user(request):
        return _login_redirect()
    form = await request.form()
    if not _csrf_ok(request, form):
        return PlainTextResponse("CSRF 校验失败", status_code=400)
    _ensure_valid_id(comment_id)
    if not repo.delete_comment(comment_id):
        raise HTTPException(status_code=404)
    return RedirectResponse("/admin/comments?status=all&ok=comment_deleted", status_code=303)


# ---------------------------------------------------------------- 设置 / 密码


@router.get("/admin/settings", response_class=HTMLResponse)
def settings_page(request: Request):
    if not _current_user(request):
        return _login_redirect()
    return render_admin(
        request,
        "admin/settings.html",
        active_nav="settings",
        error=None,
        page_title="设置",
    )


@router.post("/admin/settings")
async def save_settings(request: Request):
    if not _current_user(request):
        return _login_redirect()
    form = await request.form()
    if not _csrf_ok(request, form):
        return PlainTextResponse("CSRF 校验失败", status_code=400)

    try:
        per_page = int(str(form.get("posts_per_page") or "8"))
    except ValueError:
        per_page = 8
    per_page = max(1, min(50, per_page))

    values = {
        "site_title": _field(form, "site_title", 80) or "纸上",
        "site_subtitle": _field(form, "site_subtitle", 120),
        "site_description": _field(form, "site_description", 300),
        "author_name": _field(form, "author_name", 80) or "纸上",
        "author_bio": _field(form, "author_bio", 300),
        "footer_text": _field(form, "footer_text", 200),
        "about_md": str(form.get("about_md") or "")[:50000],
        "posts_per_page": str(per_page),
        "allow_comments": "1"
        if str(form.get("allow_comments") or "") in ("1", "on", "true", "yes")
        else "0",
    }
    repo.update_settings(values)
    return RedirectResponse("/admin/settings?ok=settings_saved", status_code=303)


@router.post("/admin/password")
async def change_password(request: Request):
    user = _current_user(request)
    if not user:
        return _login_redirect()
    form = await request.form()
    if not _csrf_ok(request, form):
        return PlainTextResponse("CSRF 校验失败", status_code=400)

    current = str(form.get("current_password") or "")
    new_password = str(form.get("new_password") or "")
    confirm = str(form.get("confirm_password") or "")

    db_user = repo.get_user_by_id(int(user["id"]))
    error = None
    if db_user is None:
        error = "账号不存在，请重新登录。"
    elif not auth.verify_password(current, db_user["password_hash"]):
        error = "当前密码不正确。"
    elif len(new_password) < 6:
        error = "新密码至少 6 位。"
    elif len(new_password) > 200:
        error = "新密码过长。"
    elif new_password != confirm:
        error = "两次输入的新密码不一致。"

    if error:
        return render_admin(
            request,
            "admin/settings.html",
            active_nav="settings",
            error=error,
            page_title="设置",
            status_code=400,
        )

    new_version = repo.update_user_password(
        int(user["id"]), auth.hash_password(new_password)
    )
    response = RedirectResponse("/admin/settings?ok=password_changed", status_code=303)
    if new_version is not None:
        token = auth.create_session(
            int(user["id"]), str(user["username"]), new_version
        )
        auth.set_session_cookie(response, token)
    return response


# ---------------------------------------------------------------- Markdown 预览


@router.post("/admin/preview")
async def preview(request: Request):
    # 只读接口（不修改任何状态），因此不要求 CSRF token。
    if not _current_user(request):
        return JSONResponse({"error": "未登录"}, status_code=401)
    form = await request.form()
    content = str(form.get("content_md") or "")[:200000]
    return JSONResponse({"html": str(render_markdown(content))})


# ---------------------------------------------------------------- Markdown 导入

IMPORT_MAX_FILES = 50
IMPORT_MAX_FILE_BYTES = 5 * 1024 * 1024
IMPORT_MAX_CONTENT_CHARS = 200_000
IMPORT_ALLOWED_SUFFIXES = {".md", ".markdown", ".txt"}


def _import_error(filename: str, message: str) -> dict:
    return {
        "filename": filename,
        "status": "error",
        "message": message,
        "title": "",
        "slug": "",
        "edit_url": "",
        "view_url": "",
    }


def _decode_text(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("无法识别文件编码，请使用 UTF-8")


async def _import_markdown_file(
    upload, default_status: str, on_conflict: str, default_tags: str
) -> dict:
    filename = Path(upload.filename or "untitled.md").name
    if Path(filename).suffix.lower() not in IMPORT_ALLOWED_SUFFIXES:
        return _import_error(filename, "仅支持 .md / .markdown / .txt 文件")

    try:
        raw = await upload.read()
    except Exception:  # noqa: BLE001 - 上传流异常统一转换为该文件的错误结果
        return _import_error(filename, "读取上传文件失败")
    if not raw:
        return _import_error(filename, "文件内容为空")
    if len(raw) > IMPORT_MAX_FILE_BYTES:
        return _import_error(filename, "单个文件不能超过 5MB")

    try:
        text = _decode_text(raw)
    except ValueError as exc:
        return _import_error(filename, str(exc))
    if "\x00" in text:
        return _import_error(filename, "文件看起来不是文本文件")

    try:
        data, body = frontmatter.split_frontmatter(text)
    except frontmatter.FrontmatterError as exc:
        return _import_error(filename, str(exc))

    content = body.strip("\n").strip()
    if not content:
        return _import_error(filename, "正文内容为空，已跳过")
    if len(content) > IMPORT_MAX_CONTENT_CHARS:
        return _import_error(filename, "正文超过 200000 字符限制")

    title = frontmatter.extract_title(data, content, Path(filename).stem)
    if not title:
        return _import_error(filename, "无法确定文章标题")

    status = frontmatter.resolve_status(data, default_status)
    tags = normalize_tags(
        ",".join(frontmatter.extract_tags(data) + [default_tags])
    )
    summary = frontmatter.extract_summary(data)
    published_at = frontmatter.extract_published_at(data)
    slug = frontmatter.extract_slug(data) or slugify(title)
    if not slug:
        slug = (
            "imported-"
            + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
            + "-"
            + secrets.token_hex(3)
        )

    existing = repo.get_post_by_slug(slug)
    post_id: int | None = None
    result_status = "created"
    if existing is not None:
        if on_conflict == "skip":
            return {
                "filename": filename,
                "status": "skipped",
                "message": "slug 已存在，已跳过",
                "title": existing["title"],
                "slug": existing["slug"],
                "edit_url": f"/admin/posts/{existing['id']}/edit",
                "view_url": (
                    f"/post/{quote(existing['slug'])}"
                    if existing["status"] == "published"
                    else ""
                ),
            }
        post_id = int(existing["id"])
        result_status = "updated"

    saved_id = repo.save_post(
        post_id=post_id,
        title=title,
        slug=slug,
        summary=summary,
        tags=tags,
        content_md=content,
        status=status,
        published_at=published_at,
    )
    if saved_id is None:
        return _import_error(filename, "保存失败：目标文章不存在")

    saved = repo.get_post_by_id(saved_id)
    if saved is None:
        return _import_error(filename, "保存后无法读取文章")
    return {
        "filename": filename,
        "status": result_status,
        "message": "已更新" if result_status == "updated" else "已导入",
        "title": saved["title"],
        "slug": saved["slug"],
        "edit_url": f"/admin/posts/{saved_id}/edit",
        "view_url": (
            f"/post/{quote(saved['slug'])}" if saved["status"] == "published" else ""
        ),
    }


@router.get("/admin/import", response_class=HTMLResponse)
def import_page(request: Request):
    if not _current_user(request):
        return _login_redirect()
    return render_admin(
        request,
        "admin/import.html",
        active_nav="import",
        results=None,
        summary=None,
        error=None,
        page_title="导入",
    )


@router.post("/admin/import")
async def import_markdown(request: Request):
    if not _current_user(request):
        return _login_redirect()
    form = await request.form()
    if not _csrf_ok(request, form):
        return PlainTextResponse("CSRF 校验失败", status_code=400)

    uploads = [
        item
        for item in form.getlist("files")
        if hasattr(item, "filename") and hasattr(item, "read")
    ]
    status_default = str(form.get("status") or "published").strip().lower()
    if status_default not in ("published", "draft"):
        status_default = "published"
    on_conflict = str(form.get("on_conflict") or "skip").strip().lower()
    if on_conflict not in ("skip", "overwrite"):
        on_conflict = "skip"
    default_tags = normalize_tags(str(form.get("default_tags") or "")[:300])

    if not uploads:
        return render_admin(
            request,
            "admin/import.html",
            active_nav="import",
            results=None,
            summary=None,
            error="请选择至少一个 Markdown 文件（.md / .markdown / .txt）。",
            page_title="导入",
            status_code=400,
        )
    if len(uploads) > IMPORT_MAX_FILES:
        return render_admin(
            request,
            "admin/import.html",
            active_nav="import",
            results=None,
            summary=None,
            error="一次最多导入 50 个文件，请分批上传。",
            page_title="导入",
            status_code=400,
        )

    results: list[dict] = []
    for upload in uploads:
        try:
            results.append(
                await _import_markdown_file(
                    upload, status_default, on_conflict, default_tags
                )
            )
        except Exception:  # noqa: BLE001 - 单个文件失败不影响其余文件
            logger.exception(
                "导入文件失败：%s", getattr(upload, "filename", "?")
            )
            results.append(
                _import_error(
                    Path(str(getattr(upload, "filename", "untitled"))).name,
                    "导入失败，请查看服务端日志",
                )
            )

    summary = {
        "total": len(results),
        "created": sum(1 for item in results if item["status"] == "created"),
        "updated": sum(1 for item in results if item["status"] == "updated"),
        "skipped": sum(1 for item in results if item["status"] == "skipped"),
        "failed": sum(1 for item in results if item["status"] == "error"),
    }
    return render_admin(
        request,
        "admin/import.html",
        active_nav="import",
        results=results,
        summary=summary,
        error=None,
        page_title="导入",
    )
