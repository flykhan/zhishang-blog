#!/bin/sh
#
# 「纸上」博客入口脚本
#
# 职责：
#   1. 确保数据目录（默认 /data）存在；
#   2. 以 root 启动时，把数据目录交给 app 用户（UID/GID 10001），
#      然后通过 setpriv / gosu / su-exec / Python 兜底降权；
#   3. 用 exec 执行 CMD，保证 uvicorn 成为 PID 1、正确接收 SIGTERM/SIGINT。
#
# 以非 root 用户启动（如 docker run --user 1000:1000）时不做任何提权动作，直接 exec。
#
# python:3.12-slim（Debian）自带 setpriv，属于 util-linux 包，无需额外安装。

set -eu

DATA_DIR="${DATA_DIR:-/data}"
APP_UID="${APP_UID:-10001}"
APP_GID="${APP_GID:-10001}"

# 确保数据目录存在（root 或非 root 都尽力创建；已有目录时幂等）
mkdir -p "$DATA_DIR" 2>/dev/null || true

if [ "$(id -u)" = "0" ]; then
    # 修正 /data 所有权（首次挂载空卷、或从宿主机拷贝数据后可能出现 root 属主）
    if ! chown -R "$APP_UID:$APP_GID" "$DATA_DIR" 2>/dev/null; then
        echo "entrypoint: 警告：无法修改 $DATA_DIR 的所有权，尝试以 app 用户直接运行" >&2
    fi

    # 按可用性选择降权工具：setpriv > gosu > su-exec > Python 标准库兜底
    # 用 --clear-groups 而不是 --init-groups：前者不依赖 /etc/passwd 查表，
    # 即使运行环境暂时缺少 app 用户也能降权（本镜像 Dockerfile 已创建该用户）。
    if command -v setpriv >/dev/null 2>&1; then
        exec setpriv --reuid="$APP_UID" --regid="$APP_GID" --clear-groups -- "$@"
    elif command -v gosu >/dev/null 2>&1; then
        exec gosu "$APP_UID:$APP_GID" "$@"
    elif command -v su-exec >/dev/null 2>&1; then
        exec su-exec "$APP_UID:$APP_GID" "$@"
    else
        # 兜底：纯 Python 实现 setgid/setuid 后 exec（需要 python3 在 PATH 中）
        exec python3 -c '
import os
import sys

uid = int(os.environ.get("APP_UID", "10001"))
gid = int(os.environ.get("APP_GID", "10001"))
try:
    os.setgroups([])
except OSError:
    pass
os.setgid(gid)
os.setuid(uid)
os.execvp(sys.argv[1], sys.argv[1:])
' "$@"
    fi
fi

# 非 root 启动（或 chown 失败后的降级路径）：直接执行，信号由 exec 传递
exec "$@"
