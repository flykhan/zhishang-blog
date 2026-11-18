"""公共路由：首页、文章、标签、归档、搜索、关于、RSS、sitemap、健康检查。"""

from __future__ import annotations

import html
import math
import re
from datetime import datetime, timezone
from email.utils import format_datetime
from urllib.parse import quote
# 仅用于输出转义（不是解析），不存在 XXE 风险。
from xml.sax.saxutils import escape as xml_escape  # nosec B406

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    RedirectResponse,
    Response,
)

from . import auth, db, repo
from .config import settings
from .markdown_render import render_markdown
from .templating import jsonld_dumps, render
from .utils import clean_summary, comment_email_valid, parse_iso

router = APIRouter()


# ---------------------------------------------------------------- 辅助


def _per_page() -> int:
    try:
        value = int(repo.get_setting("posts_per_page", "8"))
    except (TypeError, ValueError):
        value = 8
    return max(1, min(50, value))


def _pagination(page: int, total_pages: int, total_items: int, base_url: str) -> dict:
    """base_url 指向第 1 页；第 N 页为 base_url + /page/N。"""

    def page_url(number: int) -> str:
        if number <= 1:
            return base_url
        return f"{base_url.rstrip('/')}/page/{number}"

    return {
        "page": page,
        "total_pages": total_pages,
        "total_items": total_items,
        "prev_url": page_url(page - 1) if page > 1 else None,
        "next_url": page_url(page + 1) if page < total_pages else None,
    }


def _post_url(slug: str) -> str:
    return f"/post/{quote(slug)}"


# ---------------------------------------------------------------- 分享 / SEO 辅助

# Markdown 内联图片：![alt](url) 或 ![alt](<url with space> "title")
_MD_IMAGE_RE = re.compile(r"!\[[^\]]*\]\(\s*(?:<([^>]+)>|([^)\s]+))", re.IGNORECASE)
# 内联 HTML 图片：<img src="..."> / src='...' / src=...
_HTML_IMAGE_RE = re.compile(
    r"""<img\b[^>]*?\bsrc\s*=\s*(?:"([^"]+)"|'([^']+)'|([^\s>"']+))""",
    re.IGNORECASE,
)


def _first_content_image(content_md: str) -> str:
    """取正文中位置最靠前的一张图片 URL（Markdown 或内联 HTML），没有则返回空串。"""
    if not content_md:
        return ""
    first = None
    for pattern in (_MD_IMAGE_RE, _HTML_IMAGE_RE):
        match = pattern.search(content_md)
        if match and (first is None or match.start() < first.start()):
            first = match
    if first is None:
        return ""
    for group in first.groups():
        if group and group.strip():
            return html.unescape(group.strip())
    return ""


def _absolute_image_url(url: str) -> str:
    """把正文图片 URL 归一为 og:image 可用的绝对地址。"""
    default = settings.site_url_base + "/static/og-default.png"
    if not url:
        return default
    if url.startswith("//"):  # 协议相对地址
        return "https:" + url
    scheme = re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", url)
    if scheme:
        # 已有协议：http(s) 原样使用；data:/其他协议不能作为分享图。
        return url if url.lower().startswith(("http://", "https://")) else default
    path = url[2:] if url.startswith("./") else url
    return f"{settings.site_url_base}/{path.lstrip('/')}"


def _jsonld_date(value) -> str:
    dt = parse_iso(value)
    return dt.isoformat() if dt else ""


def _article_jsonld(post: dict, site: dict, image_url: str) -> str:
    """生成文章页 Article JSON-LD（字符串，`</` 已转义）。"""
    page_url = settings.site_url_base + _post_url(post["slug"])
    published = _jsonld_date(post["published_at"] or post["created_at"])
    modified = _jsonld_date(post["updated_at"]) or published
    return jsonld_dumps(
        {
            "@context": "https://schema.org",
            "@type": "Article",
            "headline": post["title"],
            "description": clean_summary(post["summary"], 200)
            or site.get("site_description", ""),
            "image": [image_url],
            "datePublished": published,
            "dateModified": modified,
            "inLanguage": "zh-CN",
            "author": {
                "@type": "Person",
                "name": site.get("author_name", ""),
            },
            "mainEntityOfPage": {"@type": "WebPage", "@id": page_url},
            "url": page_url,
        }
    )


# ---------------------------------------------------------------- 列表 / 详情


@router.get("/", response_class=HTMLResponse)
def index(request: Request):
    return _index_page(request, 1)


@router.get("/page/{page:int}", response_class=HTMLResponse)
def index_page(request: Request, page: int):
    return _index_page(request, page)


def _index_page(request: Request, page: int):
    per_page = _per_page()
    total = repo.count_published()
    total_pages = max(1, math.ceil(total / per_page))
    clamped = min(max(1, page), total_pages)
    if clamped != page or (page == 1 and request.url.path != "/"):
        target = "/" if clamped == 1 else f"/page/{clamped}"
        return RedirectResponse(target, status_code=301)
    page = clamped
    posts = repo.list_published(per_page, (page - 1) * per_page)
    page_title = "首页" if page == 1 else f"第 {page} 页"
    return render(
        request,
        "index.html",
        posts=posts,
        pagination=_pagination(page, total_pages, total, "/"),
        page_title=page_title,
    )


@router.get("/post/{slug}", response_class=HTMLResponse)
def post_detail(request: Request, slug: str):
    post = repo.get_post_by_slug(slug)
    if post is None:
        raise HTTPException(status_code=404)
    user = getattr(request.state, "user", None)
    if post["status"] != "published" and user is None:
        raise HTTPException(status_code=404)
    if post["status"] == "published" and user is None:
        repo.increment_views(post["id"])
    post["content_html"] = str(render_markdown(post["content_md"]))
    site = repo.get_settings()
    og_image = _absolute_image_url(_first_content_image(post["content_md"]))
    comments = repo.list_approved_comments(post["id"])
    adjacent = repo.get_adjacent_posts(post)
    return render(
        request,
        "post.html",
        post=post,
        comments=comments,
        comment_count=len(comments),
        comments_open=repo.get_setting("allow_comments", "1") == "1",
        comment_submitted=request.query_params.get("ok") == "comment"
        or request.query_params.get("comment") == "ok",
        page_title=post["title"],
        og_image=og_image,
        article_jsonld=_article_jsonld(post, site, og_image),
        prev_post=adjacent["prev"],
        next_post=adjacent["next"],
        related_posts=repo.related_posts(post, limit=3),
    )


@router.post("/post/{slug}/comment")
async def submit_comment(request: Request, slug: str):
    post = repo.get_post_by_slug(slug)
    if post is None or post["status"] != "published":
        raise HTTPException(status_code=404)

    back = _post_url(slug)
    if repo.get_setting("allow_comments", "1") != "1":
        return RedirectResponse(f"{back}?err=comment_closed#comments", status_code=303)

    form = await request.form()
    author = str(form.get("author") or "").strip()
    email = str(form.get("email") or "").strip()
    content = str(form.get("content") or "").strip()
    honeypot = str(form.get("website") or "").strip()

    if honeypot:  # 蜜罐：机器人填写了隐藏字段，直接假装成功
        return RedirectResponse(f"{back}?ok=comment#comments", status_code=303)

    valid = (
        1 <= len(author) <= 60
        and 2 <= len(content) <= 2000
        and len(email) <= 120
        and (not email or comment_email_valid(email))
    )
    if not valid:
        return RedirectResponse(f"{back}?err=comment_invalid#comments", status_code=303)

    ip = auth.client_ip(request)
    if not auth.comment_allowed(ip):
        return RedirectResponse(f"{back}?err=rate_limited#comments", status_code=303)
    auth.record_comment(ip)

    repo.create_comment(post["id"], author, email, content, ip)
    return RedirectResponse(f"{back}?ok=comment#comments", status_code=303)


# ---------------------------------------------------------------- 标签 / 搜索 / 归档


@router.get("/tags", response_class=HTMLResponse)
def tags_page(request: Request):
    return render(request, "tags.html", tags=repo.all_tags(), page_title="标签")


@router.get("/tag/{tag}", response_class=HTMLResponse)
def tag_page(request: Request, tag: str):
    return _tag_page(request, tag, 1)


@router.get("/tag/{tag}/page/{page:int}", response_class=HTMLResponse)
def tag_page_numbered(request: Request, tag: str, page: int):
    return _tag_page(request, tag, page)


def _tag_page(request: Request, tag: str, page: int):
    tag = tag.strip()[:40]
    per_page = _per_page()
    total = repo.count_posts_by_tag(tag)
    total_pages = max(1, math.ceil(total / per_page))
    clamped = min(max(1, page), total_pages)
    if clamped != page or request.url.path.endswith("/page/1"):
        target = (
            f"/tag/{quote(tag)}"
            if clamped == 1
            else f"/tag/{quote(tag)}/page/{clamped}"
        )
        return RedirectResponse(target, status_code=301)
    page = clamped
    posts = repo.list_posts_by_tag(tag, per_page, (page - 1) * per_page)
    return render(
        request,
        "tag.html",
        tag=tag,
        posts=posts,
        pagination=_pagination(page, total_pages, total, f"/tag/{quote(tag)}"),
        page_title=f"标签：{tag}",
    )


@router.get("/search", response_class=HTMLResponse)
def search(request: Request):
    query = (request.query_params.get("q") or "").strip()[:80]
    posts = repo.search_posts(query) if query else []
    return render(
        request,
        "search.html",
        query=query,
        posts=posts,
        total=repo.count_search_posts(query) if query else 0,
        page_title=f"搜索：{query}" if query else "搜索",
    )


@router.get("/archive", response_class=HTMLResponse)
def archive(request: Request):
    return render(request, "archive.html", groups=repo.archive_groups(), page_title="归档")


@router.get("/about", response_class=HTMLResponse)
def about(request: Request):
    return render(request, "about.html", page_title="关于")


# ---------------------------------------------------------------- Feed / SEO / 健康检查


@router.get("/feed.xml")
def feed():
    site = repo.get_settings()
    base = settings.site_url_base
    posts = repo.list_published(20, 0)

    items: list[str] = []
    for post in posts:
        dt = parse_iso(post["published_at"]) or parse_iso(post["created_at"])
        pub_date = format_datetime(dt) if dt else ""
        link = f"{base}{_post_url(post['slug'])}"
        items.append(
            "<item>"
            f"<title>{xml_escape(post['title'])}</title>"
            f"<link>{xml_escape(link)}</link>"
            f'<guid isPermaLink="true">{xml_escape(link)}</guid>'
            f"<pubDate>{pub_date}</pubDate>"
            f"<description>{xml_escape(clean_summary(post['summary']))}</description>"
            "</item>"
        )

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0"><channel>'
        f"<title>{xml_escape(site.get('site_title', '纸上'))}</title>"
        f"<link>{xml_escape(base)}</link>"
        f"<description>{xml_escape(site.get('site_description', ''))}</description>"
        "<language>zh-CN</language>"
        f"<lastBuildDate>{format_datetime(datetime.now(timezone.utc))}</lastBuildDate>"
        + "".join(items)
        + "</channel></rss>"
    )
    return Response(content=xml, media_type="application/rss+xml; charset=utf-8")


@router.get("/sitemap.xml")
def sitemap():
    base = settings.site_url_base
    urls: list[str] = []
    for path in ("/", "/archive", "/tags", "/about"):
        urls.append(f"<url><loc>{xml_escape(base + path)}</loc></url>")
    for post in repo.list_published(500, 0):
        dt = parse_iso(post["updated_at"]) or parse_iso(post["created_at"])
        lastmod = (
            f"<lastmod>{dt.astimezone(settings.timezone).strftime('%Y-%m-%d')}</lastmod>"
            if dt
            else ""
        )
        urls.append(
            f"<url><loc>{xml_escape(base + _post_url(post['slug']))}</loc>{lastmod}</url>"
        )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        + "".join(urls)
        + "</urlset>"
    )
    return Response(content=xml, media_type="application/xml; charset=utf-8")


@router.get("/robots.txt")
def robots():
    return PlainTextResponse(
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /admin\n"
        "\n"
        f"Sitemap: {settings.site_url_base}/sitemap.xml\n"
    )


@router.get("/healthz")
def healthz():
    try:
        with db.get_conn() as con:
            con.execute("SELECT 1").fetchone()
    except Exception:  # pragma: no cover - 仅在数据库异常时触发
        return JSONResponse({"status": "error"}, status_code=503)
    return JSONResponse({"status": "ok", "service": "paper-blog"})


@router.get("/favicon.ico")
def favicon():
    # 本轮新增了 ICO/SVG 两套图标：浏览器直接请求 /favicon.ico 时交给静态 ICO。
    return RedirectResponse("/static/favicon.ico", status_code=302)
