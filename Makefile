.PHONY: help install run stop restart status logs clean docker-up docker-down docker-restart

PYTHON ?= python3
PIP ?= pip3
PORT ?= 8000
PID_FILE = .server.pid
LOG_DIR = logs

help: ## Показать справку
	@echo "╔══════════════════════════════════════════════╗"
	@echo "║  Auto-Reg Codex — Makefile                   ║"
	@echo "╚══════════════════════════════════════════════╝"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

# ─── Зависимости ───────────────────────────────────────

install: ## Установить зависимости
	$(PIP) install -r requirements.txt

install-dev: ## Установить зависимости (dev)
	$(PIP) install -r requirements.txt
	$(PIP) install -e ".[dev]"

# ─── Запуск / Остановка ───────────────────────────────

run: ## Запустить сервер (foreground)
	$(PYTHON) webui.py

start: ## Запустить сервер (background)
	@if [ -f $(PID_FILE) ] && kill -0 $$(cat $(PID_FILE)) 2>/dev/null; then \
		echo "⚠️  Сервер уже запущен (PID $$(cat $(PID_FILE)))"; \
	else \
		nohup $(PYTHON) webui.py > $(LOG_DIR)/server.log 2>&1 & \
		echo $$! > $(PID_FILE); \
		sleep 2; \
		if kill -0 $$(cat $(PID_FILE)) 2>/dev/null; then \
			echo "✅ Сервер запущен (PID $$(cat $(PID_FILE))) → http://localhost:$(PORT)"; \
		else \
			echo "❌ Сервер не запустился, см. $(LOG_DIR)/server.log"; \
			rm -f $(PID_FILE); \
		fi \
	fi

stop: ## Остановить сервер
	@if [ -f $(PID_FILE) ]; then \
		PID=$$(cat $(PID_FILE)); \
		if kill -0 $$PID 2>/dev/null; then \
			kill $$PID; \
			echo "🛑 Сервер остановлен (PID $$PID)"; \
		else \
			echo "⚠️  Процесс $$PID уже не работает"; \
		fi; \
		rm -f $(PID_FILE); \
	else \
		echo "⚠️  PID-файл не найден, ищу процесс на порту $(PORT)..."; \
		PID=$$(lsof -ti:$(PORT) 2>/dev/null | head -1); \
		if [ -n "$$PID" ]; then \
			kill $$PID; \
			echo "🛑 Остановлен процесс $$PID на порту $(PORT)"; \
		else \
			echo "ℹ️  Сервер не запущен"; \
		fi \
	fi

restart: stop start ## Перезапустить сервер

status: ## Статус сервера
	@if [ -f $(PID_FILE) ] && kill -0 $$(cat $(PID_FILE)) 2>/dev/null; then \
		echo "✅ Сервер работает (PID $$(cat $(PID_FILE))) → http://localhost:$(PORT)"; \
	else \
		PID=$$(lsof -ti:$(PORT) 2>/dev/null | head -1); \
		if [ -n "$$PID" ]; then \
			echo "✅ Сервер работает (PID $$PID) → http://localhost:$(PORT)"; \
		else \
			echo "⭕ Сервер не запущен"; \
		fi \
	fi

logs: ## Показать логи сервера (live)
	@if [ -f $(LOG_DIR)/server.log ]; then \
		tail -f $(LOG_DIR)/server.log; \
	else \
		echo "ℹ️  Лог-файл не найден. Запустите: make start"; \
	fi

# ─── Docker ────────────────────────────────────────────

docker-up: ## Запустить через Docker Compose
	docker-compose up -d --build

docker-down: ## Остановить Docker Compose
	docker-compose down

docker-restart: docker-down docker-up ## Перезапустить Docker

docker-logs: ## Логи Docker
	docker-compose logs -f

# ─── Утилиты ──────────────────────────────────────────

clean: ## Очистить кеш и временные файлы
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	rm -f $(PID_FILE)

check: ## Проверить синтаксис Python
	$(PYTHON) -m py_compile webui.py
	@find src -name "*.py" -exec $(PYTHON) -m py_compile {} \;
	@echo "✅ Все файлы скомпилированы без ошибок"
