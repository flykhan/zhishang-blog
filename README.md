# 「纸上」— 自托管 Markdown 博客系统

**纸上** 是一个自托管的单用户博客系统。服务端渲染、无前端构建、无 CDN 依赖，克隆下来一条 `docker compose up -d --build` 就能拥有一个干净、耐读、完全离线可运行的写作空间。

- **形态**：FastAPI + Jinja2 服务端渲染的多页应用，SQLite 单文件存储
- **风格**：文艺杂志 / 纸质手账感，衬线大标题、窄栏排版、赤陶色点缀
- **交付**：多阶段 Docker 构建，非 root 运行，数据卷持久化，内置健康检查

---

## 目录

- [功能特性](#功能特性)
- [技术栈](#技术栈)
- [快速开始（Docker）](#快速开始docker)
- [本地开发](#本地开发)
- [环境变量](#环境变量)
- [目录结构](#目录结构)
- [数据备份与恢复](#数据备份与恢复)
- [安全建议](#安全建议)
- [常用命令](#常用命令)
- [冒烟测试](#冒烟测试)
- [常见问题（FAQ）](#常见问题faq)

---

## 功能特性

- **Markdown 写作**：标准 Markdown 渲染，编辑页支持实时预览、字数统计、`Ctrl/Cmd+S` 保存
- **草稿 / 发布**：草稿仅后台可见，发布后进入首页、归档、标签、RSS 与 sitemap
- **标签与归档**：标签聚合、按年份归档、按标签筛选
- **站内搜索**：标题 / 摘要 / 正文关键词检索
- **RSS 与 sitemap**：自动生成 `/feed.xml`、`/sitemap.xml`、`/robots.txt`，便于订阅与搜索引擎收录
- **关于页**：独立 Markdown 页面，可放作者简介与站点说明
- **评论系统**：匿名评论，**默认需要后台审核**后才公开；内置蜜罐字段防垃圾评论
- **后台管理**：登录、仪表盘、文章管理、评论审核、站点设置、修改密码
- **站点设置**：标题、副标题、描述、作者信息、页脚、关于页、每页文章数、评论开关
- **深色模式**：跟随系统或手动切换，`localStorage` 持久化，无闪烁
- **响应式**：360px–1440px 自适应，手机 / 平板 / 桌面均可阅读
- **无外部依赖**：不引用任何 CDN、在线字体、第三方 JS/CSS，可完全离线运行
- **容器友好**：非 root（UID 10001）、`/data` 数据卷、`HEALTHCHECK`、优雅停机

---

## 技术栈

| 层 | 选型 |
|---|---|
| Web 框架 | FastAPI + Uvicorn |
| 模板 | Jinja2（`StrictUndefined`，服务端渲染） |
| 存储 | SQLite（Python 标准库 `sqlite3`） |
| Markdown | `markdown`（Python） |
| 前端 | 原生 HTML / CSS / JavaScript，无构建步骤 |
| 运行时 | Python 3.12（Docker）；本地 3.9+ |
| 部署 | Docker 多阶段构建 + Docker Compose |

---

## 快速开始（Docker）

### 前置要求

- Docker 24+
- Docker Compose **v2.24+**（使用 `env_file.required: false` 需要该版本；更低版本请先手动创建 `.env`）

### 一条命令启动

```bash
git clone <仓库地址> myblog
cd myblog

# 可选：准备环境变量（不创建也能直接启动，全部有默认值）
cp .env.example .env
# 按需修改 .env，重点：ADMIN_PASSWORD、SECRET_KEY、SITE_URL

docker compose up -d --build
```

启动后访问：

| 页面 | 地址 |
|---|---|
| 前台首页 | http://localhost:8080 |
| 后台登录 | http://localhost:8080/admin/login |

> **默认管理员账号：`admin` / `admin123`**，仅用于首次初始化，登录后请立即在「后台 → 设置 → 修改密码」中修改。
> 若未设置 `SECRET_KEY`，后端会自动生成并保存到 `/data/.secret_key`，重启后会话不会失效。

### 检查状态

```bash
docker compose ps          # STATUS 一列显示 healthy 即正常
docker compose logs -f     # 查看日志
curl http://localhost:8080/healthz   # {"status":"ok"}
```

停止服务（**保留数据**）：

```bash
docker compose down
```

需要升级版本时：

```bash
git pull
docker compose up -d --build   # 数据卷 blog-data 会保留
```

---

## 本地开发

本地开发不依赖 Docker，只需 Python 3.9+：

```bash
python3 -m venv .venv
source .venv/bin/activate           # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 使用本地数据目录（默认 ./data/blog.db，首次启动自动建表并创建管理员）
export DB_PATH=./data/blog.db
export SITE_URL=http://localhost:8000
export ADMIN_USERNAME=admin
export ADMIN_PASSWORD=admin123

uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

打开 <http://localhost:8000>。首次启动日志中会出现默认管理员密码的提示警告。

> 本地 SQLite 文件位于 `./data/blog.db`（已被 `.gitignore` 忽略），删除它即可重置全站数据。

---

## 环境变量

所有变量均有安全缺省值，**缺少 `.env` 也能直接启动**。`docker compose` 会自动读取项目根目录的 `.env` 用于变量插值，并注入容器。

| 变量 | 默认值 | 说明 |
|---|---|---|
| `SECRET_KEY` | 自动生成并持久化到 `/data/.secret_key` | 会话签名密钥。生产环境建议显式设置随机值，更换后所有登录会话失效 |
| `DB_PATH` | `./data/blog.db`（容器内 `/data/blog.db`） | SQLite 数据库路径；compose 中固定为 `/data/blog.db` |
| `ADMIN_USERNAME` | `admin` | 首次初始化管理员用户名（仅数据库为空时生效） |
| `ADMIN_PASSWORD` | `admin123` | 首次初始化管理员密码（启动日志会给出警告） |
| `SITE_URL` | `http://localhost:8080` | RSS / sitemap 绝对链接前缀，部署公网时改成真实域名 |
| `SITE_TZ` | `Asia/Shanghai` | 展示时区（数据库始终以 UTC 存储） |
| `BLOG_PORT` | `8080` | 宿主机映射端口（容器内固定 8000） |
| `ALLOW_COMMENTS` | `true` | 评论功能的初始化默认值（之后以后台设置为准） |
| `COOKIE_SECURE` | `false` | HTTPS 部署时设为 `true`，Cookie 带 Secure 标记 |
| `SESSION_MAX_AGE` | `604800`（7 天） | 会话有效期（秒） |

生成 `SECRET_KEY` 的方法：

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

示例 `.env`：

```dotenv
SECRET_KEY=替换为上面命令生成的随机字符串
ADMIN_PASSWORD=替换为强密码
SITE_URL=https://blog.example.com
BLOG_PORT=8080
COOKIE_SECURE=true
```

修改环境变量后重新应用：

```bash
docker compose up -d
```

---

## 目录结构

```text
myblog/
├── SPEC.md                  # 接口契约与实现规范（开发文档）
├── requirements.txt         # Python 依赖
├── app/                     # 应用源码
│   ├── main.py              # FastAPI 入口（app.main:app）
│   ├── config.py            # 环境变量与配置
│   ├── db.py                # SQLite 初始化与连接
│   ├── auth.py              # 登录会话 / CSRF
│   ├── repo.py              # 数据访问层
│   ├── utils.py             # 通用工具
│   ├── markdown_render.py   # Markdown 渲染
│   ├── routes_public.py     # 前台路由
│   ├── routes_admin.py      # 后台路由
│   ├── templates/           # Jinja2 模板
│   └── static/              # CSS / JS / favicon（无外部依赖）
├── docker/
│   └── entrypoint.sh        # 容器入口：修正 /data 权限后降权 exec
├── scripts/
│   └── smoke_test.sh        # 端到端冒烟测试（bash + curl）
├── Dockerfile               # 多阶段构建
├── docker-compose.yml       # 一键部署
├── .dockerignore
├── .env.example             # 环境变量示例
├── Makefile                 # 常用命令封装
├── README.md
└── data/                    # 本地运行时 SQLite（已被 git 忽略）
```

容器内的数据布局：

```text
/data/
├── blog.db          # SQLite 数据库（文章、评论、设置、用户）
└── .secret_key      # 未显式设置 SECRET_KEY 时自动生成
```

---

## 数据备份与恢复

数据全部保存在 Docker 卷 `blog-data` 中，核心是单文件 SQLite 数据库 `/data/blog.db`。

### 方式一：在线备份数据库（推荐，无需停机）

利用 Python 标准库 `sqlite3.backup()` 做一致性快照，再复制到宿主机：

```bash
# 1. 在容器内生成一致性快照
docker compose exec -T blog python -c \
  "import sqlite3; s=sqlite3.connect('/data/blog.db'); d=sqlite3.connect('/data/blog.db.bak'); s.backup(d); d.close(); s.close()"

# 2. 复制到宿主机
docker compose cp blog:/data/blog.db.bak "./blog-backup-$(date +%Y%m%d-%H%M%S).db"

# 3. 清理容器内临时快照
docker compose exec -T blog rm -f /data/blog.db.bak
```

### 方式二：备份整个数据卷（含 SECRET_KEY）

停机后打包整个卷更彻底，适合迁移服务器：

```bash
docker compose stop blog
docker run --rm -v blog-data:/data -v "$PWD":/backup alpine \
  tar czf "/backup/blog-data-$(date +%Y%m%d).tar.gz" -C /data .
docker compose start blog
```

> 未设置 `SECRET_KEY` 时，密钥保存在 `/data/.secret_key`。迁移或恢复时一并保留可避免所有用户被强制重新登录。

### 恢复

**恢复数据库文件**（服务已停止，避免覆盖正在使用的数据库）：

```bash
docker compose stop blog

# 用备份覆盖容器卷中的数据库（--entrypoint 绕过降权入口，以 root 写入卷）
docker compose run --rm --no-deps --entrypoint sh blog \
  -c 'cat > /data/blog.db' < blog-backup-20261118-093000.db
docker compose run --rm --no-deps --entrypoint sh blog \
  -c 'chown 10001:10001 /data/blog.db'

docker compose start blog
```

**恢复整个数据卷**：

```bash
docker compose down
docker volume rm blog-data
docker volume create blog-data
docker run --rm -v blog-data:/data -v "$PWD":/backup alpine \
  sh -c 'tar xzf /backup/blog-data-20261118.tar.gz -C /data && chown -R 10001:10001 /data'
docker compose up -d
```

> 备份文件包含站点全部内容，请妥善保管并避免提交到版本库（`.gitignore` 已忽略 `*.db` 与 `backups/`）。

---

## 安全建议

1. **立即修改默认密码**：首次登录后进入「后台 → 设置 → 修改密码」，不要长期使用 `admin123`。
2. **显式设置 `SECRET_KEY`**：在 `.env` 中使用随机值（`python -c "import secrets; print(secrets.token_hex(32))"`），并妥善保管 `.env`。
3. **生产环境务必启用 HTTPS**：通过 Nginx / Caddy 等反向代理终止 TLS，并设置 `COOKIE_SECURE=true`、`SITE_URL=https://你的域名`。
4. **不要直接暴露后台端口到公网**：仅将 8080 映射到本机（如 `127.0.0.1:8080:8000`），由反向代理对外提供服务；或使用防火墙 / 内网访问。
5. **限制管理入口**：如需更高安全性，可在反向代理层对 `/admin` 增加 IP 白名单或额外认证。
6. **定期备份**：按上文方案定期备份数据库与 `.secret_key`，并验证恢复流程。
7. **及时更新**：关注基础镜像与应用依赖的安全更新，升级后重新构建镜像。
8. **评论默认审核**：保持评论审核开启，避免垃圾内容直接公开。

### 反向代理示例

Caddy（自动申请证书）：

```caddyfile
blog.example.com {
    reverse_proxy 127.0.0.1:8080
}
```

Nginx（TLS 由 certbot 等管理）：

```nginx
server {
    listen 443 ssl;
    http2 on;
    server_name blog.example.com;

    ssl_certificate     /etc/letsencrypt/live/blog.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/blog.example.com/privkey.pem;

    client_max_body_size 2m;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

此时修改 `.env`：

```dotenv
SITE_URL=https://blog.example.com
COOKIE_SECURE=true
# 公网部署时建议改成只绑定本机，由反向代理访问
# BLOG_PORT=8080（配合 compose 端口改为 127.0.0.1:8080:8000）
```

---

## 常用命令

项目提供 Makefile 封装：

```bash
make help      # 查看所有目标
make init      # 从 .env.example 生成 .env
make build     # 构建镜像
make up        # 后台启动（首次自动构建）
make down      # 停止并移除容器（保留数据卷）
make restart   # 重启服务
make logs      # 跟踪日志
make ps        # 查看状态
make shell     # 进入容器 shell
make smoke     # 执行冒烟测试
make clean     # 停止并删除容器、数据卷与镜像（危险：删除所有数据）
```

不习惯 make 时直接用 compose：

```bash
docker compose up -d --build
docker compose logs -f
docker compose down
```

---

## 冒烟测试

`scripts/smoke_test.sh` 使用纯 bash + curl（不需要 jq / Python），对运行中的实例执行端到端验证：

```bash
# 默认：http://localhost:8080，管理员 admin/admin123
./scripts/smoke_test.sh

# 自定义地址与账号（环境变量或位置参数均可）
BASE_URL=http://localhost:8080 ADMIN_USER=admin ADMIN_PASS=你的密码 ./scripts/smoke_test.sh
./scripts/smoke_test.sh http://localhost:8080 admin 你的密码
```

覆盖链路：

1. `GET /healthz` 健康检查
2. 登录（cookie jar，从登录页解析 `csrf_token`）
3. 新建并发布文章（`status=published`）
4. 首页与文章详情页可见
5. `/feed.xml` RSS 可访问且包含新文章
6. 后台设置页可访问
7. 匿名提交评论（应进入待审核状态、暂不公开）
8. 后台审核通过评论
9. 文章页出现已审核评论
10. 删除文章，文章页返回 404
11. 退出登录，后台访问被重定向到登录页

每一步输出 `[PASS]` / `[FAIL]`，结束时汇总；存在失败时退出码为 `1`，可直接接入 CI：

```bash
docker compose up -d --build
make smoke
```

---

## 常见问题（FAQ）

### 1. 端口 8080 被占用 / 想换端口

在 `.env` 中修改 `BLOG_PORT`，然后 `docker compose up -d`：

```dotenv
BLOG_PORT=9090
```

容器内始终监听 8000，只有宿主机映射端口变化。

### 2. 忘记管理员密码怎么办

系统目前不提供邮件找回。建议：

- 若有数据库备份，按[恢复](#恢复)流程回滚到修改密码前；
- 若已无可用密码且数据可以接受丢失，可删除数据卷重新初始化：
  ```bash
  docker compose down -v
  docker compose up -d --build
  ```
  随后使用 `.env` 中的 `ADMIN_USERNAME` / `ADMIN_PASSWORD` 首次初始化（**会丢失全部文章与评论**，务必先备份）。

### 3. 修改 `.env` 后不生效

环境变量在容器创建时注入，修改后需要重建容器：

```bash
docker compose up -d --force-recreate
```

### 4. 启动后容器状态一直是 `unhealthy`

```bash
docker compose logs --tail=200 blog
docker compose exec blog python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/healthz').read())"
```

常见原因是应用启动异常（如依赖缺失、端口被占、数据库权限问题），日志会给出具体堆栈。

### 5. 数据库权限错误 / `unable to open database file`

入口脚本会以 root 修正 `/data` 所有权后降权到 UID 10001。如果手动拷贝过数据导致属主异常，可执行：

```bash
docker compose run --rm --no-deps --entrypoint sh blog -c 'chown -R 10001:10001 /data'
docker compose restart blog
```

### 6. 修改 `SECRET_KEY` 后所有人都要重新登录

这是预期行为：`SECRET_KEY` 用于签名会话 Cookie，更换后旧会话全部失效。

### 7. 评论提交成功但前台看不到

评论默认需要审核。登录后台 → 「评论」→ 待审列表 → 点击「通过」，刷新文章页即可看到。若站点设置中关闭了评论，前台将不显示评论表单。

### 8. 时区/日期显示不对

设置 `SITE_TZ`（如 `Asia/Shanghai`）后重建容器。数据库中的时间始终以 UTC 保存，仅展示时区不同。

### 9. 能离线/内网部署吗

可以。页面不引用任何外部 CDN、在线字体或第三方脚本，镜像构建完成后可完全离线运行。首次构建需要能访问 PyPI 拉取 Python 依赖。

### 10. 支持 ARM64 / 树莓派吗

基础镜像 `python:3.12-slim` 提供多架构版本，`docker compose build` 会在本机架构上正常构建。

### 11. 如何升级并保留数据

```bash
git pull
docker compose up -d --build
```

数据保存在命名卷 `blog-data` 中，重建镜像不会影响文章、评论与设置。升级前建议先备份。

---

## 许可

本项目为自托管个人使用而编写，可自由修改与部署。第三方依赖遵循各自许可证。
