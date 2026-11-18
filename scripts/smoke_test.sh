#!/usr/bin/env bash
#
# 「纸上」博客系统 — 端到端冒烟测试
#
# 依赖：bash + curl（不依赖 jq / python），适用于宿主机或 CI。
#
# 用法：
#   ./scripts/smoke_test.sh
#   BASE_URL=http://localhost:8080 ADMIN_USER=admin ADMIN_PASS=admin123 ./scripts/smoke_test.sh
#   ./scripts/smoke_test.sh http://localhost:8080 admin admin123
#
# 覆盖链路：
#   /healthz → 登录（cookie jar + 从登录页解析 csrf_token）→ 新建并发布文章
#   → 首页与文章页可见 → RSS → 后台设置页 → 提交评论 → 后台审核通过
#   → 文章页出现评论 → 删除文章 → 退出登录
#
# 每一步输出 [PASS]/[FAIL]，结束时汇总；存在失败时退出码为 1。

set -u

BASE_URL="${BASE_URL:-${1:-http://localhost:8080}}"
ADMIN_USER="${ADMIN_USER:-${2:-admin}}"
ADMIN_PASS="${ADMIN_PASS:-${3:-admin123}}"
BASE_URL="${BASE_URL%/}"

STAMP="$(date +%s)"
TITLE="冒烟测试文章 ${STAMP}"
SLUG="smoke-test-${STAMP}"
SUMMARY="这是一篇由冒烟测试自动创建的文章。"
CONTENT_MD="## 冒烟测试

这是脚本自动生成的内容，用于验证发布、展示、评论与删除链路。

- 时间戳：${STAMP}"
COMMENT="冒烟测试评论 ${STAMP}"

PASS=0
FAIL=0
POST_ID=""
POST_DELETED=0

TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/zhishang-smoke.XXXXXX")"
JAR="$TMP_DIR/cookies.txt"

cleanup() {
  # 测试中途失败时尽量清理掉本脚本创建的文章，避免污染博客
  if [ -n "${POST_ID}" ] && [ "${POST_DELETED:-0}" -eq 0 ]; then
    local html="$TMP_DIR/cleanup.html" csrf=""
    if curl -sS --max-time 10 -b "$JAR" -c "$JAR" -o "$html" \
        "${BASE_URL}/admin/posts" 2>/dev/null; then
      csrf="$(extract_csrf "$html")"
      if [ -n "$csrf" ]; then
        curl -sS --max-time 10 -o /dev/null -b "$JAR" -c "$JAR" -X POST \
          --data-urlencode "csrf_token=${csrf}" \
          "${BASE_URL}/admin/posts/${POST_ID}/delete" 2>/dev/null || true
      fi
    fi
  fi
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

# ---------------------------------------------------------------------------
# 输出与断言辅助
# ---------------------------------------------------------------------------
section() { printf '\n== %s ==\n' "$1"; }
ok()      { PASS=$((PASS + 1)); printf '  [PASS] %s\n' "$1"; }
bad()     { FAIL=$((FAIL + 1)); printf '  [FAIL] %s\n' "$1"; }

# check_code 名称 期望码 实际码
check_code() {
  if [ "$2" = "$3" ]; then
    ok "$1（HTTP $3）"
  else
    bad "$1（期望 HTTP $2，实际 $3）"
  fi
}

# 从 HTML 中解析 <input ... name="csrf_token" ... value="...">
extract_csrf() {
  local html_file="$1" token=""
  token="$(tr '\n' ' ' < "$html_file" \
    | grep -oE '<input[^>]*name="csrf_token"[^>]*>' \
    | head -n 1 \
    | sed -E 's/.*value="([^"]*)".*/\1/')"
  if [ -z "$token" ]; then
    token="$(tr '\n' ' ' < "$html_file" \
      | grep -oE '<meta[^>]*name="csrf-token"[^>]*>' \
      | head -n 1 \
      | sed -E 's/.*content="([^"]*)".*/\1/')"
  fi
  printf '%s' "$token"
}

# http_get URL 输出文件 [额外 curl 参数...]，回显状态码
http_get() {
  local url="$1" out="$2" code=""
  shift 2
  code="$(curl -sS --max-time 20 -b "$JAR" -c "$JAR" -o "$out" -w '%{http_code}' "$@" "$url" 2>/dev/null)" || true
  [ -n "$code" ] || code="000"
  printf '%s' "$code"
}

# http_post URL 输出文件 [表单/其它参数...]，回显状态码
http_post() {
  local url="$1" out="$2" code=""
  shift 2
  code="$(curl -sS --max-time 20 -b "$JAR" -c "$JAR" -o "$out" -w '%{http_code}' \
    -X POST "$@" "$url" 2>/dev/null)" || true
  [ -n "$code" ] || code="000"
  printf '%s' "$code"
}

contains() { grep -qF -- "$2" "$1" 2>/dev/null; }

# 在管理文章列表中定位文章 id
# 说明：真实模板中 <tr>、标题与操作链接各自独占一行，直接按行匹配无法把 slug 与
# 文章 id 关联起来。这里先把整个页面压成一行，再在每个 </tr> 后断行，保证
# 「一行 = 一个表格行」，然后在该行内提取 /admin/posts/<id>。返回 id 后调用方
# 还会打开编辑页二次校验，避免误删其它文章。
extract_post_id() {
  local html_file="$1" slug="$2" row id end
  for end in '</tr>' '</li>' '</article>'; do
    row="$(tr '\n' ' ' < "$html_file" \
      | sed "s|${end}|${end}\\n|g" \
      | grep -F -- "$slug" | head -n 1)"
    if [ -n "$row" ]; then
      id="$(printf '%s' "$row" | grep -oE '/admin/posts/[0-9]+' | head -n 1 | grep -oE '[0-9]+')"
      if [ -n "$id" ]; then
        printf '%s' "$id"
        return 0
      fi
    fi
  done
  return 1
}

# 在待审评论列表中找到可审核的评论 id
extract_comment_id() {
  local html_file="$1"
  grep -oE '/admin/comments/[0-9]+/approve' "$html_file" 2>/dev/null \
    | head -n 1 | grep -oE '[0-9]+'
}

usage() {
  sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'
}

case "${1:-}" in
  -h | --help)
    usage
    exit 0
    ;;
esac

printf '「纸上」博客冒烟测试\n'
printf '  BASE_URL   : %s\n' "$BASE_URL"
printf '  管理员     : %s\n' "$ADMIN_USER"
printf '  测试文章   : %s（/%s）\n' "$TITLE" "$SLUG"

# ---------------------------------------------------------------------------
# 1. 健康检查
# ---------------------------------------------------------------------------
section '健康检查 GET /healthz'
HEALTH_CODE="$(http_get "$BASE_URL/healthz" "$TMP_DIR/healthz.json")"
check_code '健康检查返回 200' '200' "$HEALTH_CODE"
if contains "$TMP_DIR/healthz.json" '"ok"'; then
  ok '健康检查响应包含 "ok"'
else
  bad '健康检查响应未包含 "ok"'
fi

# ---------------------------------------------------------------------------
# 2. 登录（cookie jar + 从登录页解析 CSRF）
# ---------------------------------------------------------------------------
section '后台登录'
LOGIN_GET_CODE="$(http_get "$BASE_URL/admin/login" "$TMP_DIR/login.html")"
check_code '登录页可访问' '200' "$LOGIN_GET_CODE"
LOGIN_CSRF="$(extract_csrf "$TMP_DIR/login.html")"
if [ -n "$LOGIN_CSRF" ]; then
  ok '从登录页解析到 csrf_token'
else
  bad '未能从登录页解析 csrf_token'
fi

LOGIN_POST_CODE="$(http_post "$BASE_URL/admin/login" "$TMP_DIR/login_post.html" \
  --data-urlencode "username=${ADMIN_USER}" \
  --data-urlencode "password=${ADMIN_PASS}" \
  --data-urlencode "csrf_token=${LOGIN_CSRF}")"
check_code '登录（默认成功应 303 跳转）' '303' "$LOGIN_POST_CODE"

DASH_CODE="$(http_get "$BASE_URL/admin" "$TMP_DIR/dashboard.html")"
check_code '登录后可访问后台仪表盘' '200' "$DASH_CODE"
DASH_CSRF="$(extract_csrf "$TMP_DIR/dashboard.html")"
if [ -n "$DASH_CSRF" ]; then
  ok '从后台页面解析到 csrf_token'
else
  bad '未能从后台页面解析 csrf_token'
fi

# ---------------------------------------------------------------------------
# 3. 新建文章（status=published）
# ---------------------------------------------------------------------------
section '新建并发布文章'
NEW_CODE="$(http_get "$BASE_URL/admin/posts/new" "$TMP_DIR/editor.html")"
check_code '编辑器页面可访问' '200' "$NEW_CODE"

SAVE_CODE="$(http_post "$BASE_URL/admin/posts/save" "$TMP_DIR/saved.html" \
  --data-urlencode "id=" \
  --data-urlencode "title=${TITLE}" \
  --data-urlencode "slug=${SLUG}" \
  --data-urlencode "summary=${SUMMARY}" \
  --data-urlencode "tags=冒烟测试" \
  --data-urlencode "content_md=${CONTENT_MD}" \
  --data-urlencode "status=published" \
  --data-urlencode "csrf_token=${DASH_CSRF}")"
check_code '保存文章（发布）' '303' "$SAVE_CODE"

# ---------------------------------------------------------------------------
# 4. 首页与文章页可见
# ---------------------------------------------------------------------------
section '前台可见性'
HOME_CODE="$(http_get "$BASE_URL/" "$TMP_DIR/home.html")"
check_code '首页可访问' '200' "$HOME_CODE"
if contains "$TMP_DIR/home.html" "$TITLE"; then
  ok '首页可见新发布文章'
else
  bad '首页未找到新发布文章'
fi

POST_CODE="$(http_get "$BASE_URL/post/${SLUG}" "$TMP_DIR/post.html")"
check_code '文章详情页可访问' '200' "$POST_CODE"
if contains "$TMP_DIR/post.html" "$TITLE"; then
  ok '文章详情页显示标题'
else
  bad '文章详情页未显示标题'
fi

# ---------------------------------------------------------------------------
# 5. RSS
# ---------------------------------------------------------------------------
section 'RSS 订阅'
FEED_CODE="$(http_get "$BASE_URL/feed.xml" "$TMP_DIR/feed.xml")"
check_code 'RSS 可访问' '200' "$FEED_CODE"
if contains "$TMP_DIR/feed.xml" '<rss'; then
  ok 'RSS 返回内容为 RSS 2.0'
else
  bad 'RSS 返回内容缺少 <rss> 标记'
fi
if contains "$TMP_DIR/feed.xml" "$TITLE"; then
  ok 'RSS 包含新发布文章'
else
  bad 'RSS 未包含新发布文章'
fi

# ---------------------------------------------------------------------------
# 6. 后台设置页
# ---------------------------------------------------------------------------
section '后台设置页'
SETTINGS_CODE="$(http_get "$BASE_URL/admin/settings" "$TMP_DIR/settings.html")"
check_code '后台设置页可访问' '200' "$SETTINGS_CODE"
SETTINGS_CSRF="$(extract_csrf "$TMP_DIR/settings.html")"
if [ -n "$SETTINGS_CSRF" ]; then
  ok '设置页包含 csrf_token'
else
  bad '设置页缺少 csrf_token'
fi

# ---------------------------------------------------------------------------
# 7. 提交评论（匿名，待审核）
# ---------------------------------------------------------------------------
section '提交评论'
COMMENT_CODE="$(http_post "$BASE_URL/post/${SLUG}/comment" "$TMP_DIR/comment_post.html" \
  --data-urlencode "author=冒烟测试" \
  --data-urlencode "email=smoke@example.com" \
  --data-urlencode "content=${COMMENT}" \
  --data-urlencode "website=")"
check_code '提交评论' '303' "$COMMENT_CODE"

PENDING_CODE="$(http_get "$BASE_URL/post/${SLUG}" "$TMP_DIR/post_pending.html")"
check_code '提交后文章页可访问' '200' "$PENDING_CODE"
if contains "$TMP_DIR/post_pending.html" "$COMMENT"; then
  bad '待审核评论不应公开显示'
else
  ok '待审核评论未公开显示'
fi

# ---------------------------------------------------------------------------
# 8. 后台审核通过评论
# ---------------------------------------------------------------------------
section '后台审核评论'
COMMENTS_CODE="$(http_get "$BASE_URL/admin/comments?status=pending" "$TMP_DIR/comments.html")"
check_code '待审评论列表可访问' '200' "$COMMENTS_CODE"
COMMENT_ID="$(extract_comment_id "$TMP_DIR/comments.html")"
if [ -n "$COMMENT_ID" ]; then
  ok "找到待审评论 id=${COMMENT_ID}"
else
  bad '待审评论列表中未找到评论 id'
fi

if [ -n "$COMMENT_ID" ]; then
  COMMENTS_CSRF="$(extract_csrf "$TMP_DIR/comments.html")"
  APPROVE_CODE="$(http_post "$BASE_URL/admin/comments/${COMMENT_ID}/approve" "$TMP_DIR/approve.html" \
    --data-urlencode "csrf_token=${COMMENTS_CSRF}")"
  check_code '审核通过评论' '303' "$APPROVE_CODE"
else
  bad '跳过审核：缺少评论 id'
fi

# ---------------------------------------------------------------------------
# 9. 评论出现在文章页
# ---------------------------------------------------------------------------
section '评论公开可见'
POST_AFTER_CODE="$(http_get "$BASE_URL/post/${SLUG}" "$TMP_DIR/post_after.html")"
check_code '文章页可访问' '200' "$POST_AFTER_CODE"
if contains "$TMP_DIR/post_after.html" "$COMMENT"; then
  ok '审核通过后评论出现在文章页'
else
  bad '审核通过后文章页未出现评论'
fi

# ---------------------------------------------------------------------------
# 10. 删除文章
# ---------------------------------------------------------------------------
section '删除文章'
LIST_CODE="$(http_get "$BASE_URL/admin/posts?status=all" "$TMP_DIR/admin_posts.html")"
check_code '后台文章列表可访问' '200' "$LIST_CODE"
POST_ID="$(extract_post_id "$TMP_DIR/admin_posts.html" "$SLUG" || true)"
if [ -n "$POST_ID" ]; then
  ok "定位到文章 id=${POST_ID}"
  # 二次校验：打开编辑页确认该 id 确实对应本次测试文章（防止误删其它文章）
  EDIT_CHECK_CODE="$(http_get "$BASE_URL/admin/posts/${POST_ID}/edit" "$TMP_DIR/edit_check.html")"
  if [ "$EDIT_CHECK_CODE" = "200" ] && contains "$TMP_DIR/edit_check.html" "$SLUG"; then
    ok "编辑页校验文章 id=${POST_ID} 与测试 slug 一致"
  else
    bad "文章 id=${POST_ID} 校验失败，跳过删除"
    POST_ID=""
  fi
else
  bad '后台文章列表中未定位到测试文章 id'
fi

if [ -n "$POST_ID" ]; then
  DELETE_CSRF="$(extract_csrf "$TMP_DIR/admin_posts.html")"
  DELETE_CODE="$(http_post "$BASE_URL/admin/posts/${POST_ID}/delete" "$TMP_DIR/deleted.html" \
    --data-urlencode "csrf_token=${DELETE_CSRF}")"
  check_code '删除文章' '303' "$DELETE_CODE"
  POST_DELETED=1
else
  bad '跳过删除：缺少文章 id'
fi

GONE_CODE="$(http_get "$BASE_URL/post/${SLUG}" "$TMP_DIR/post_gone.html")"
check_code '删除后文章页返回 404' '404' "$GONE_CODE"

# ---------------------------------------------------------------------------
# 11. 退出登录
# ---------------------------------------------------------------------------
section '退出登录'
LOGOUT_CSRF="$(extract_csrf "$TMP_DIR/dashboard.html")"
if [ -z "$LOGOUT_CSRF" ]; then
  http_get "$BASE_URL/admin" "$TMP_DIR/dashboard2.html" >/dev/null
  LOGOUT_CSRF="$(extract_csrf "$TMP_DIR/dashboard2.html")"
fi
LOGOUT_CODE="$(http_post "$BASE_URL/admin/logout" "$TMP_DIR/logout.html" \
  --data-urlencode "csrf_token=${LOGOUT_CSRF}")"
check_code '退出登录' '303' "$LOGOUT_CODE"

AFTER_LOGOUT_CODE="$(http_get "$BASE_URL/admin" "$TMP_DIR/after_logout.html")"
check_code '退出后访问后台被重定向' '303' "$AFTER_LOGOUT_CODE"

# ---------------------------------------------------------------------------
# 汇总
# ---------------------------------------------------------------------------
printf '\n----------------------------------------\n'
printf '结果：%d 通过，%d 失败\n' "$PASS" "$FAIL"
if [ "$FAIL" -ne 0 ]; then
  printf '冒烟测试失败\n'
  exit 1
fi
printf '冒烟测试通过\n'
exit 0
