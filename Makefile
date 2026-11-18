# 「纸上」博客系统 — Makefile
#
# 常用命令：
#   make build    构建镜像
#   make up       后台启动（首次会自动构建）
#   make smoke    对运行中的服务执行冒烟测试
#   make logs     跟踪日志
#   make clean    停止并删除容器、网络、数据卷和镜像（会删除所有数据！）

.DEFAULT_GOAL := help
SHELL := /bin/sh

COMPOSE ?= docker compose
SERVICE ?= blog
IMAGE   ?= zhishang-blog:latest
BASE_URL ?= http://localhost:8080

.PHONY: help init build up down logs ps restart smoke test clean shell

help: ## 显示帮助
	@printf '%s\n' \
	  '「纸上」博客系统' \
	  '' \
	  '用法: make <目标>' \
	  '' \
	  '  init     从 .env.example 生成 .env（已存在则跳过）' \
	  '  build    构建 Docker 镜像' \
	  '  up       后台启动服务（docker compose up -d --build）' \
	  '  down     停止并移除容器（保留数据卷）' \
	  '  restart  重启服务' \
	  '  logs     跟踪查看服务日志' \
	  '  ps       查看服务状态' \
	  '  smoke    执行冒烟测试（也可以直接跑 scripts/smoke_test.sh）' \
	  '  test     smoke 的别名' \
	  '  shell    进入运行中的容器 shell' \
	  '  clean    停止并删除容器、网络、数据卷与镜像（危险：会删除所有数据）' \
	  '' \
	  '可覆盖的变量: COMPOSE、SERVICE、IMAGE、BASE_URL'

init: ## 从 .env.example 生成 .env
	@if [ -f .env ]; then \
	  echo '.env 已存在，跳过（如需重新生成请先手动删除）'; \
	else \
	  cp .env.example .env && echo '已生成 .env，请按需编辑（尤其是 SECRET_KEY / ADMIN_PASSWORD）'; \
	fi

build: ## 构建镜像
	$(COMPOSE) build

up: init ## 后台启动
	$(COMPOSE) up -d --build

down: ## 停止并移除容器（保留数据卷）
	$(COMPOSE) down --remove-orphans

restart: ## 重启服务
	$(COMPOSE) restart $(SERVICE)

logs: ## 跟踪日志
	$(COMPOSE) logs -f --tail=200 $(SERVICE)

ps: ## 查看状态
	$(COMPOSE) ps

smoke: ## 冒烟测试
	BASE_URL="$(BASE_URL)" ./scripts/smoke_test.sh

test: smoke ## smoke 的别名

shell: ## 进入容器 shell
	$(COMPOSE) exec $(SERVICE) sh

clean: ## 清除容器、数据卷与镜像（会删除所有数据！）
	@echo '!! 即将删除容器、数据卷与镜像，所有博客数据都会丢失。'
	$(COMPOSE) down --volumes --remove-orphans
	-@docker image rm $(IMAGE) 2>/dev/null || true
	@echo '清理完成。'
