# syntax=docker/dockerfile:1
#
# 「纸上」博客系统 — 多阶段构建
#   builder: 只负责安装 Python 依赖，安装到 /install 前缀
#   runtime: python:3.12-slim，仅拷贝安装产物与 app/，无编译工具残留
#
# 构建: docker build -t zhishang-blog .
# 运行: docker run -d -p 8080:8000 -v blog-data:/data --name blog zhishang-blog

# ---------- Stage 1: builder ----------
FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /build

# 依赖全部是纯 Python / 自带 wheel，不需要 gcc。若未来新增需要编译的依赖，
# 请只在本阶段 apt-get 安装 build-essential，runtime 阶段不受影响。
COPY requirements.txt ./
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ---------- Stage 2: runtime ----------
FROM python:3.12-slim AS runtime

LABEL org.opencontainers.image.title="纸上博客" \
      org.opencontainers.image.description="自托管单用户 Markdown 博客系统" \
      org.opencontainers.image.licenses="MIT"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    DATA_DIR=/data \
    DB_PATH=/data/blog.db

# 非 root 运行：固定 UID/GID 10001（用户与用户组均名为 app）
# 不用 --system（系统账号 UID 上限 999，10001 会触发 useradd 警告）
RUN groupadd --gid 10001 app \
 && useradd --uid 10001 --gid app \
        --home-dir /app --no-create-home --shell /usr/sbin/nologin app \
 && mkdir -p /data /app \
 && chown app:app /data

# 仅拷贝已安装的依赖（/install 前缀 → /usr/local，与官方镜像的 Python 路径一致）
COPY --from=builder /install /usr/local

WORKDIR /app

# 仅拷贝应用代码，源码归 app 用户所有
COPY --chown=app:app app ./app

# 入口脚本：root 时修正 /data 权限后用 setpriv 降权，exec 传递信号
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod 0755 /entrypoint.sh

# SQLite 持久化目录（容器内固定 /data）
VOLUME ["/data"]

EXPOSE 8000

# 健康检查：镜像内没有 curl，用 Python 标准库请求 /healthz
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=4)"]

STOPSIGNAL SIGTERM

ENTRYPOINT ["/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
