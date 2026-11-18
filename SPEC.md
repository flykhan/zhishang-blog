# 「纸上」博客系统 — 接口契约与实现规范 (SPEC)

> **本文件由 Lead 维护，任何队友不得修改。**
> 开始工作前请完整阅读本文件。所有实现必须严格遵守这里的契约；如发现契约问题，向 Lead 报告，不要自行改动契约。

## 1. 项目概述

一个自托管单用户博客系统，项目名 **「纸上」**，位于 `/root/dsh_workspace/myblog`。

- **形态**：服务端渲染的多页应用（无需 Node 构建、无 CDN 依赖、可完全离线运行）
- **技术栈**：Python 3.12 (Docker) / 3.9+ (本地) + FastAPI + Jinja2 + SQLite（标准库 sqlite3）
- **功能**：Markdown 文章、草稿/发布、标签、归档、站内搜索、RSS、sitemap、关于页、评论（需审核）、后台登录、站点设置、深色模式、响应式
- **交付**：多阶段 Dockerfile + docker-compose，一条 `docker compose up -d --build` 启动

## 2. 目录结构与文件归属

```
myblog/
├── SPEC.md                         # Lead（只读契约）
├── requirements.txt                # Lead
├── app/
│   ├── __init__.py                 # Lead
│   ├── config.py                   # Lead
│   ├── db.py                       # Lead
│   ├── auth.py                     # Lead
│   ├── repo.py                     # Lead
│   ├── utils.py                    # Lead
│   ├── markdown_render.py          # Lead
│   ├── routes_public.py            # Lead
│   ├── routes_admin.py             # Lead
│   ├── main.py                     # Lead
│   ├── templates/
│   │   ├── base.html               # 队友 A
│   │   ├── _pagination.html        # 队友 A
│   │   ├── index.html              # 队友 A
│   │   ├── post.html               # 队友 A
│   │   ├── tags.html               # 队友 A
│   │   ├── tag.html                # 队友 A
│   │   ├── search.html             # 队友 A
│   │   ├── archive.html            # 队友 A
│   │   ├── about.html              # 队友 A
│   │   ├── 404.html                # 队友 A
│   │   └── admin/
│   │       ├── base.html           # 队友 B
│   │       ├── login.html          # 队友 B
│   │       ├── dashboard.html      # 队友 B
│   │       ├── posts.html          # 队友 B
│   │       ├── editor.html         # 队友 B
│   │       ├── comments.html       # 队友 B
│   │       └── settings.html       # 队友 B
│   └── static/
│       ├── style.css               # 队友 A
│       ├── app.js                  # 队友 A
│       ├── favicon.svg             # 队友 A
│       ├── admin.css               # 队友 B
│       └── admin.js                # 队友 B
├── docker/entrypoint.sh            # 队友 C
├── Dockerfile                      # 队友 C
├── docker-compose.yml              # 队友 C
├── .dockerignore                   # 队友 C
├── .env.example                    # 队友 C
├── .gitignore                      # 队友 C
├── Makefile                        # 队友 C
├── scripts/smoke_test.sh           # 队友 C
├── README.md                       # 队友 C
└── data/                           # 运行时 SQLite（gitignore，不入库）
```

**铁律：只改自己名下的文件。** 不要创建额外文件（临时验证脚本放 `/tmp`）。不要修改 `SPEC.md`。

## 3. 数据模型（SQLite）

时间戳统一为 ISO-8601 UTC 字符串，如 `2026-11-18T09:30:00+00:00`。

```sql
users(id INTEGER PK, username TEXT UNIQUE, password_hash TEXT, created_at TEXT)

posts(id INTEGER PK, slug TEXT UNIQUE, title TEXT, summary TEXT DEFAULT '',
      content_md TEXT DEFAULT '', tags TEXT DEFAULT '', status TEXT DEFAULT 'draft',
      views INTEGER DEFAULT 0, created_at TEXT, updated_at TEXT, published_at TEXT)
-- status ∈ 'draft' | 'published'

comments(id INTEGER PK, post_id INTEGER REFERENCES posts(id) ON DELETE CASCADE,
         author TEXT, email TEXT DEFAULT '', content TEXT,
         status TEXT DEFAULT 'pending', created_at TEXT, ip TEXT DEFAULT '')
-- status ∈ 'pending' | 'approved'

settings(key TEXT PK, value TEXT)
```

`posts.tags` 存储为逗号分隔、无空格、已去重的原始标签串，例如 `技术,FastAPI,随笔`。
默认设置键：`site_title, site_subtitle, site_description, author_name, author_bio, footer_text, about_md, posts_per_page, allow_comments`。
`footer_text` 中的 `{year}` 由后端替换为当前年份。

## 4. 全局模板上下文与过滤器

所有模板（含后台）渲染时都会注入：

| 变量 | 类型 | 说明 |
|---|---|---|
| `site` | dict[str,str] | 全部站点设置；`allow_comments` 为 `"1"`/`"0"`，`posts_per_page` 为数字字符串 |
| `user` | dict \| None | `{"id":..,"username":..}`，未登录为 None |
| `csrf` | str | 当前会话 CSRF token；未登录时为空串 |
| `flash` | list[dict] | `[{"kind": "ok"\|"err", "text": "..."}]`，来自 `?ok=` / `?err=` 白名单码 |
| `request` | Request | Starlette Request |
| `now_year` | int | 当前年份 |
| `page_title` | str | 传入 `<title>` |

Jinja 过滤器（后端已注册，模板直接用）：

| 过滤器 | 用法 | 结果 |
|---|---|---|
| `date` | `{{ post.published_at|date }}` / `{{ p.created_at\|date("%Y-%m") }}` | 默认 `2026年11月18日`；空值返回 `""` |
| `md` | `{{ site.about_md|md }}` | 渲染 Markdown 为安全 HTML（Markup） |
| `taglist` | `{{ post.tags|taglist }}` | `["技术","随笔"]` |
| `excerpt` | `{{ text|excerpt(80) }}` | 纯文本截断 |
| `reading_time` | `{{ post.content_md|reading_time }}` | 整数分钟（最少 1） |

Jinja 环境：`autoescape=True`、`trim_blocks`、`lstrip_blocks`。**未定义变量会报错**（StrictUndefined），模板只能使用本文档列出的变量和过滤器。不要用自定义 Jinja 扩展/标签。

模板中所有站内链接使用**绝对路径**（`/`、`/post/xxx`、`/admin/...`），静态资源用 `/static/...`。不要假设 `url_for` 之类 helper 存在。

## 5. 公共路由契约

| 方法 | 路径 | 模板 | 说明 |
|---|---|---|---|
| GET | `/` | index.html | 首页第 1 页 |
| GET | `/page/{page}` | index.html | 第 N 页（>1 时 canonical 指向自身） |
| GET | `/post/{slug}` | post.html | 文章详情，已发布才可见；浏览量 +1 |
| POST | `/post/{slug}/comment` | — | 提交评论→303 到 `/post/{slug}?ok=comment#comments` |
| GET | `/tags` | tags.html | 全部标签 |
| GET | `/tag/{tag}` | tag.html | 标签筛选 |
| GET | `/search` | search.html | `?q=` 关键词检索（标题/摘要/正文） |
| GET | `/archive` | archive.html | 按年份归档 |
| GET | `/about` | about.html | 关于页 |
| GET | `/feed.xml` | — | RSS 2.0（后端生成） |
| GET | `/sitemap.xml` | — | 站点地图（后端生成） |
| GET | `/robots.txt` | — | 后端生成 |
| GET | `/healthz` | — | JSON `{"status":"ok"}` |
| GET | `/favicon.ico` | — | 302 到 `/static/favicon.svg` |

404：`404.html`（公共模板，状态码 404）。500 未捕获错误返回纯文本（开发期可见）。

### 各公共模板上下文

**index.html**
- `posts`: list[dict]，每项 `{id, slug, title, summary, tags, published_at, views, reading_time}`
- `pagination`: `{page:int, total_pages:int, total_items:int, prev_url:str|None, next_url:str|None}`
- `page_title`: `"首页"` 或 `"第 2 页"`

**post.html**
- `post`: `{id, slug, title, summary, content_md, content_html, tags, status, views, created_at, updated_at, published_at, reading_time}`
- `comments`: list[dict] 已审核评论 `{id, author, content, created_at}`
- `comment_count`: int
- `comments_open`: bool（= `site.allow_comments == "1"`）
- `comment_submitted`: bool（`?comment=ok`）
- `page_title`: 文章标题

**tags.html**：`tags`: list[`{name:str, count:int}`]（按数量降序、名称升序）
**tag.html**：`tag`: str；`posts`: 同 index；`pagination`；`page_title`: `"标签: <tag>"`（模板自行拼接也可）
**search.html**：`query`: str；`posts`: list[dict]（最多 50 条，无分页）；`total`: int
**archive.html**：`groups`: list[`{year:int, posts: list[{slug,title,published_at}]}`]（年份降序、组内时间降序）
**about.html**：无额外变量（用 `site.about_md|md`、`site.author_name`、`site.author_bio`）

> index/tag 的文章卡片统一展示：日期、标题（链接）、摘要、标签、"约 X 分钟"。
> 空状态用 `.empty` 组件，如"还没有文章"。

### 评论提交
表单字段：`author`（必填 ≤60）、`email`（选填 ≤120）、`content`（必填 2–2000 字）、`website`（**蜜罐**，必须为空，否则静默丢弃并返回 `?ok=comment`）。
校验失败 → 303 到 `/post/{slug}?err=comment_invalid#comments`；评论关闭 → `?err=comment_closed`。
成功后评论状态为 `pending`，不公开展示，返回 `?ok=comment#comments`（页面提示"评论已提交，审核后显示"）。

## 6. 后台路由契约

未登录访问任何 `/admin/*`（除 login）→ 303 到 `/admin/login`。

| 方法 | 路径 | 模板 | 说明 |
|---|---|---|---|
| GET | `/admin/login` | admin/login.html | 若已登录 → 302 `/admin` |
| POST | `/admin/login` | — | 字段 `username,password,csrf_token`；成功 303 `/admin`，失败回显错误 |
| POST | `/admin/logout` | — | 校验 CSRF，清 cookie → 303 `/admin/login?ok=logged_out` |
| GET | `/admin` | admin/dashboard.html | 仪表盘 |
| GET | `/admin/posts` | admin/posts.html | 全部文章，`?status=all\|published\|draft&page=N` |
| GET | `/admin/posts/new` | admin/editor.html | 新建 |
| GET | `/admin/posts/{id}/edit` | admin/editor.html | 编辑 |
| POST | `/admin/posts/save` | — | 新建/更新（`id` 为空则新建） |
| POST | `/admin/posts/{id}/delete` | — | 删除（级联删评论） |
| POST | `/admin/posts/{id}/toggle` | — | 草稿↔发布切换 |
| GET | `/admin/comments` | admin/comments.html | `?status=pending\|approved\|all&page=N` |
| POST | `/admin/comments/{id}/approve` | — | 通过 |
| POST | `/admin/comments/{id}/delete` | — | 删除 |
| GET | `/admin/settings` | admin/settings.html | 站点设置 |
| POST | `/admin/settings` | — | 保存站点设置 |
| POST | `/admin/password` | — | 修改密码 |
| POST | `/admin/preview` | JSON | `{"html": "..."}`，编辑页实时预览 |

后台写操作全部要求 POST + CSRF 隐藏字段 `csrf_token`（与 `csrf` 值一致），不匹配 → 400。
所有 POST 成功后 303 重定向并带 `?ok=`；错误带 `?err=`（或回显 `error` 变量）。

### 后台模板上下文

**admin/base.html**：`active_nav` ∈ `"dashboard"|"posts"|"new"|"comments"|"settings"`；`pending_comments`: int；`page_title`；`csrf`；`flash` 等全局变量。

**login.html**（独立整页，不继承后台导航）：`csrf`（登录 CSRF，来自 cookie，字段名 `csrf_token`）、`username`、`error`: str|None。

**dashboard.html**：
- `stats`: `{published:int, drafts:int, views:int, comments_pending:int, comments_total:int}`
- `posts`: 最近 10 篇，`{id,title,slug,status,views,published_at,updated_at}`
- `recent_comments`: 最近 5 条（任意状态），`{id,author,content,status,created_at,post_title,post_slug}`

**posts.html**：
- `posts`: `{id,title,slug,status,views,created_at,updated_at,published_at}`
- `pagination`: 同公共分页但 URL 为 `/admin/posts?status=..&page=..`
- `status_filter`: `"all"|"published"|"draft"`
- `counts`: `{all:int, published:int, drafts:int}`

**editor.html**：
- `post`: dict|None（字段 `id,title,slug,summary,tags,content_md,status`）
- `error`: str|None

**comments.html**：
- `comments`: `{id,author,email,content,status,created_at,post_title,post_slug}`
- `pagination`: URL `/admin/comments?status=..&page=..`
- `status_filter`: `"pending"|"approved"|"all"`
- `counts`: `{pending:int, approved:int}`

**settings.html**：全局 `site` 即当前设置（字段见 §3）；`error`: str|None。密码表单独立提交到 `/admin/password`。

### 表单字段名（必须完全一致）
- 文章：`id,title,slug,summary,tags,content_md,status,csrf_token`；status 为 `draft|published`
- 设置：`site_title,site_subtitle,site_description,author_name,author_bio,footer_text,about_md,posts_per_page,allow_comments,csrf_token`；`allow_comments` 复选框 value=`1`（不勾选即关闭）
- 密码：`current_password,new_password,confirm_password,csrf_token`
- 登录：`username,password,csrf_token`

### 状态码语义（flash 码）
`?ok=`：`saved`(已保存) `deleted`(已删除) `published`(已发布) `unpublished`(已转为草稿) `approved` `comment_deleted` `settings_saved` `password_changed` `login` `logged_out` `comment`(评论已提交，待审核)
`?err=`：`notfound` `invalid`(表单有误) `wrong_password` `rate_limited` `comment_closed` `comment_invalid` `forbidden` `bad_request` `empty`
后端负责把码转成中文文案放进 `flash`；模板只需循环渲染 `flash`。

## 7. 设计系统（前台 A 与后台 B 共用 token）

`style.css` 必须在 `:root` 定义以下变量，`[data-theme="dark"]` 覆盖颜色。admin.css 可直接使用这些变量。

```css
:root{
  --font-sans: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
    "Hiragino Sans GB", "Microsoft YaHei", "Noto Sans SC", sans-serif;
  --font-serif: "Iowan Old Style", "Palatino Linotype", Palatino, "Songti SC",
    "Noto Serif SC", "Source Han Serif SC", Georgia, serif;
  --font-mono: ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace;
  --bg:#faf8f4; --bg-elev:#ffffff; --text:#1d1c1a; --muted:#6f6a61;
  --border:#e7e1d7; --accent:#b4532a; --accent-soft:rgba(180,83,42,.10);
  --code-bg:#f2ede4; --radius:10px; --maxw:720px;
  --shadow:0 1px 2px rgba(0,0,0,.04), 0 8px 24px rgba(0,0,0,.05);
}
[data-theme="dark"]{
  --bg:#141412; --bg-elev:#1c1b19; --text:#e9e5dc; --muted:#a09a8f;
  --border:#2c2a26; --accent:#e08a5f; --accent-soft:rgba(224,138,95,.14);
  --code-bg:#201f1c; --shadow:0 1px 2px rgba(0,0,0,.4), 0 8px 24px rgba(0,0,0,.25);
}
```

主题约定：`<html data-theme="light|dark">`；`localStorage["theme"]` 持久化；无存储时跟随 `prefers-color-scheme`；两套界面各自的 head 内联脚本负责防闪烁（FOUC）。`color-scheme` 同步。

**公共界面视觉方向**（队友 A）：文艺杂志 / 纸质手账感。衬线大标题、正文 17–18px / 行高 1.85、窄栏 720px、大量留白、赤陶色强调、细边框分隔、卡片悬停极轻微上浮。360px–1440px 响应式，深色模式必须好看。禁止外部字体/CDN/图标库；图标用内联 SVG 或 Unicode。

**后台界面视觉方向**（队友 B）：干净高效的工具型 UI。顶栏 + 导航、卡片化内容区、表格、状态胶囊（published=绿 / draft=灰）、编辑器左右分栏（左表单右预览，桌面 sticky 预览，移动端上下堆叠）、底部操作栏。同样响应式 + 深色模式。

## 8. 公共模板必备结构（队友 A）

- `base.html`：`<!doctype html lang="zh-CN">`、meta viewport/description、`{% block title %}`、RSS link、`/static/style.css`、favicon、主题内联脚本、header（站点标题 + 导航：首页/归档/标签/关于 + 搜索入口 + 主题切换按钮 `#theme-toggle` + 已登录时"管理"入口）、`{% block content %}`、footer（`site.footer_text`，处理 `{year}` 已由后端替换）、`/static/app.js`。
- 搜索：`<form action="/search" method="get">`，input `name="q"`，`value="{{ query|default('') }}"`（`query` 仅在 search.html 存在，base.html 不要引用它）。
- 每页 `<title>`：`{% block title %}` 默认站点标题；详情页为 `文章标题 · 站点标题`。
- `post.html`：article + `.prose` 渲染 `post.content_html|safe`；标签、发布时间、阅读时长、浏览量；评论列表 `#comments` + 表单（含蜜罐 `website` 用 `.sr-only` 或 `display:none` 隐藏）；`comment_submitted` 为 true 时显示提示；`flash` 也要显示。
- `_pagination.html`：`{% macro render(pagination) %}`，输出上一页/下一页/第 X / Y 页，`prev_url`/`next_url` 为空时不渲染链接。调用：`{% from "_pagination.html" import render with context %}`。
- 404 页面：大号 404 + 返回首页。
- `app.js`（原生 JS，无依赖）：主题切换（写 localStorage，更新按钮 aria-label 与图标）、移动端导航（如需要）、`prefers-color-scheme` 监听（仅未手动设置时）、可选阅读进度条 / 返回顶部。
- 可访问性：skip link、`aria-label`、`:focus-visible` 明显焦点环、语义化标签、对比度达标。

## 9. 后台模板必备结构（队友 B）

- `admin/base.html`：`<html data-theme>`、`/static/style.css` + `/static/admin.css`、自己的防闪烁内联脚本、顶栏（品牌「纸上」+ 导航：仪表盘/文章/写文章/评论（带待审数量徽标）/设置 + 主题切换 `#admin-theme-toggle` + 退出登录 POST 表单带 `csrf_token`）、`{% block content %}`、`/static/admin.js`。
- `login.html`：独立居中登录卡片（不继承 base，自带 HTML 骨架，引用 style.css + admin.css），用户名/密码/`csrf_token`，显示 `error`，返回首页链接。
- `dashboard.html`：4–5 张统计卡片（文章/草稿/浏览/待审评论）、最近文章表格（标题/状态/时间/操作：编辑、查看、发布切换、删除）、最近评论列表（通过/删除按钮）。
- `posts.html`：状态筛选 tabs（全部/已发布/草稿，带计数）、表格（标题/状态/浏览/更新时间/操作）、分页、新建按钮。
- `editor.html`：标题、slug（placeholder 提示留空自动生成）、标签（逗号分隔）、摘要（可空自动生成）、Markdown textarea（`#content-md`）、状态 select、保存按钮；右侧实时预览 `#preview`（JS debounce 300ms POST `/admin/preview`，`FormData: content_md`，渲染返回 HTML）；字数统计；`Ctrl/Cmd+S` 保存；删除按钮（`confirm` 二次确认）；`post.status == "published"` 时提供"查看"链接 `/post/{slug}`；`error` 展示。
- `comments.html`：tabs（待审/已通过/全部 + 计数）、评论卡片（作者、邮箱、时间、文章链接、内容、通过/删除按钮）、分页、空状态。
- `settings.html`：两组表单（站点设置 / 关于页 Markdown）+ 修改密码表单；展示当前值到 `site.*`；保存成功 flash（全局 `flash` 已渲染在 base）。
- `admin.js`：主题切换、预览请求（失败时显示错误提示而非崩溃）、Ctrl/Cmd+S、字数统计、删除确认（`data-confirm` 通用）、移动端导航折叠。
- 所有按钮/输入框 label、`aria`、`:focus-visible` 齐备。

## 10. 基础设施契约（队友 C）

- **Dockerfile**：多阶段构建（builder `pip install --prefix` → runtime `python:3.12-slim`），非 root 用户运行（UID 10001，用户/组 `app`），`/data` 数据卷（SQLite 持久化），入口脚本修正 `/data` 权限后降权执行，`EXPOSE 8000`，`HEALTHCHECK` 请求 `/healthz`，`CMD uvicorn app.main:app --host 0.0.0.0 --port 8000`。镜像要求：无编译工具残留、体积尽量小、`PYTHONDONTWRITEBYTECODE=1`、`PYTHONUNBUFFERED=1`。
- **入口脚本** `docker/entrypoint.sh`：`set -eu`；确保 `$DATA_DIR`（默认 `/data`）存在；root 时 chown 给 app 用户；用 `setpriv`/`gosu` 或 Python 降权后 `exec "$@"`；信号正常传递。
- **docker-compose.yml**：服务 `blog`，`build: .`，端口 `${BLOG_PORT:-8080}:8000`，卷 `blog-data:/data`，`restart: unless-stopped`，healthcheck，环境变量（见 §11），可选 `env_file: .env`。**注意**：compose 文件里不要用 `${SECRET_KEY:?...}` 之类强制报错语法，缺省值要能让 `docker compose up` 直接跑通。
- **.env.example**：全部环境变量 + 说明 + 生成 SECRET_KEY 的提示（`python -c "import secrets;print(secrets.token_hex(32))"`）。
- **.dockerignore**：`.git`、`data`、`__pycache__`、`*.pyc`、`.venv`、`README.md`? 保留 README 无妨，排除开发产物与本地数据库。
- **Makefile**：`build/up/down/logs/ps/restart/test(冒烟)/clean/shell` 目标。
- **scripts/smoke_test.sh**：纯 curl + bash，参数 `BASE_URL`（默认 `http://localhost:8080`）与 `ADMIN_USER/ADMIN_PASS`（默认 admin/admin123），覆盖：`/healthz`、`/`、登录（cookie jar）、新建文章、文章页可见、RSS、`/admin/settings`、提交评论、后台通过评论、评论出现在文章页、删除文章。每步打印 PASS/FAIL，任一失败退出码非 0。
- **README.md**：项目介绍、功能、截图占位（不需要真截图）、快速开始（Docker）、本地开发、环境变量表、目录结构、数据备份、安全建议（改默认密码、设置 SECRET_KEY、反向代理 HTTPS）、常见问题。中文撰写。

### §11 环境变量（后端实现，运维使用）

| 变量 | 默认 | 说明 |
|---|---|---|
| `SECRET_KEY` | 自动生成并持久化到 `/data/.secret_key` | 会话签名密钥 |
| `DB_PATH` | `./data/blog.db`（容器内 `/data/blog.db`） | SQLite 路径 |
| `ADMIN_USERNAME` | `admin` | 首次初始化管理员 |
| `ADMIN_PASSWORD` | `admin123` | 首次初始化密码（启动日志警告） |
| `SITE_URL` | `http://localhost:8080` | RSS/sitemap 绝对链接前缀 |
| `SITE_TZ` | `Asia/Shanghai` | 展示时区（存储始终 UTC） |
| `BLOG_PORT` | `8080` | 宿主机端口（compose 用） |
| `ALLOW_COMMENTS` | `true` | 初始化默认值（之后以数据库设置为准） |
| `COOKIE_SECURE` | `false` | HTTPS 部署设为 true |
| `SESSION_MAX_AGE` | `604800`（7 天） | 会话有效期（秒） |

## 12. 质量门槛与自检

- 全部 HTML 通过 Jinja2 语法解析；用 `/tmp` 下临时脚本 + `StrictUndefined` + 样例上下文渲染每个模板（可 stub 过滤器），确保 0 错误。**不要**把验证脚本写进项目目录。
- 无外部网络依赖：不得引用任何 CDN、在线字体、第三方 JS/CSS。
- 响应式：360px、768px、1280px 三档检查（可用 CSS 逻辑自查）。
- 深色模式：所有新增组件都要有 `[data-theme="dark"]` 下的表现验证。
- 代码整洁：CSS 用 2 空格缩进、按区块注释；JS 用 `const/let`、严格模式、无内联事件处理器（除主题防闪烁脚本）。
- 完成后：`team_task_update` 标记自己的任务 `complete`，并用 `send_message` 向 `lead` 汇报（列出交付文件、自检结果、遗留问题/假设）。

## 13. 协作规则

- 只写自己名下文件；需要改别人文件时**报告 Lead**，不要直接改。
- 目录已建好，无需再建；如需要新目录先确认（`mkdir` 了文件归属之外的目录也算越界）。
- 后端由 Lead 同步开发，未完成前不要试图启动整站；用 `/tmp` 渲染自检即可。
- 遇到契约不明或冲突：`send_message` 给 lead，等待回复，不要猜。
