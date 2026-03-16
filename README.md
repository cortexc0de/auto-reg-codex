# Система автоматической регистрации OpenAI v2

Веб-система для автоматизированной регистрации аккаунтов OpenAI с поддержкой множества почтовых сервисов, параллельной пакетной регистрации, управления прокси и аккаунтами.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)

## Возможности

- **Поддержка нескольких почтовых сервисов**
  - Tempmail.lol (временная почта, без настройки)
  - Outlook (IMAP + XOAUTH2, поддержка массового импорта)
  - Пользовательский домен (REST API)

- **Режимы регистрации**
  - Одиночная регистрация
  - Пакетная регистрация (настраиваемое количество и интервал)
  - Пакетная регистрация через Outlook (последовательно по указанным аккаунтам)

- **Управление параллелизмом**
  - Pipeline-режим: запуск новой задачи каждые N секунд с ограничением максимального числа параллельных задач
  - Parallel-режим: все задачи запускаются одновременно, Semaphore контролирует максимум параллельных
  - Настраиваемый параллелизм (1–50) через UI
  - Смешанный вывод логов с префиксом `[Задача N]`

- **Мониторинг в реальном времени**
  - WebSocket для потоковой передачи логов
  - Автоматическое переподключение при навигации между страницами
  - Резервный режим опроса (polling)

- **Управление прокси**
  - Статическая конфигурация прокси
  - Динамический прокси (получение нового IP через API)
  - Список прокси (случайный выбор, отслеживание времени использования)

- **Управление аккаунтами**
  - Просмотр, удаление, массовые операции
  - Обновление и валидация токенов
  - Экспорт (JSON / CSV / CPA-формат)
    - Одиночный аккаунт — отдельный `.json` файл
    - Несколько аккаунтов — `.zip` архив с отдельным файлом на каждый аккаунт
  - Загрузка в CPA (Codex Protocol API, прямое подключение без прокси)
  - Управление подпиской (ручная отметка / автоопределение plus/team)
  - Загрузка в Team Manager (прямое подключение без прокси)

- **Оплата и апгрейд**
  - Генерация ссылок на оплату ChatGPT Plus или Team
  - Автоматическое открытие Chrome/Edge в режиме инкогнито на бэкенде
  - Для Team: настраиваемое имя workspace, количество мест, период оплаты

- **Системные настройки**
  - Конфигурация прокси (статический + динамический)
  - Параметры OAuth для Outlook
  - Параметры регистрации (таймаут, повторы, длина пароля и т.д.)
  - Настройка ожидания кода подтверждения
  - Настройка загрузки CPA
  - Настройка Team Manager (API URL + API Key)
  - Управление базой данных (бэкап, очистка)

## Быстрый старт

### Требования

- Python 3.10+
- [uv](https://github.com/astral-sh/uv) (рекомендуется) или pip

### Установка зависимостей

```bash
# Используя uv (рекомендуется)
uv sync

# Или используя pip
pip install -r requirements.txt
```

### Запуск Web UI

```bash
# Запуск по умолчанию (127.0.0.1:8000)
python webui.py

# Указать адрес и порт
python webui.py --host 0.0.0.0 --port 8080

# Режим отладки (горячая перезагрузка)
python webui.py --debug
```

После запуска откройте http://127.0.0.1:8000

## Сборка в исполняемый файл

```bash
# Windows
build.bat

# Linux/macOS
bash build.sh
```

После сборки будет создан `codex-register.exe` (Windows) или `codex-register` (Unix) — запускается без установки Python.

## Структура проекта

```
auto-reg-codex/
├── webui.py            # Точка входа Web UI
├── build.bat           # Скрипт сборки для Windows
├── build.sh            # Скрипт сборки для Linux/macOS
├── src/
│   ├── config/         # Управление конфигурацией (Pydantic Settings)
│   ├── core/           # Ядро (движок регистрации, HTTP-клиент, CPA, оплата, TM)
│   ├── database/       # База данных (SQLAlchemy + SQLite)
│   ├── services/       # Реализации почтовых сервисов
│   └── web/            # FastAPI веб-приложение
│       ├── app.py      # Точка входа, монтирование маршрутов
│       ├── routes/     # API-маршруты
│       ├── task_manager.py  # Менеджер задач/логов/WebSocket
│       └── routes/websocket.py  # Обработка WebSocket
├── templates/          # HTML-шаблоны Jinja2
├── static/             # Статические ресурсы (CSS / JS)
└── data/               # Данные времени выполнения (БД, логи)
```

## Стек технологий

| Уровень | Технология |
|---------|-----------|
| Веб-фреймворк | FastAPI + Uvicorn |
| База данных | SQLAlchemy + SQLite |
| Шаблонизатор | Jinja2 |
| HTTP-клиент | curl_cffi (эмуляция отпечатка браузера) |
| Реальное время | WebSocket |
| Параллелизм | asyncio Semaphore + ThreadPoolExecutor |
| Фронтенд | Нативный JavaScript (без фреймворков) |
| Сборка | PyInstaller |

## API-эндпоинты

### Задачи регистрации

| Метод | Путь | Описание |
|-------|------|----------|
| POST | `/api/registration/start` | Запуск одиночной регистрации |
| POST | `/api/registration/batch` | Запуск пакетной регистрации (`concurrency`, `mode`) |
| GET | `/api/registration/batch/{id}` | Статус пакетной задачи |
| POST | `/api/registration/batch/{id}/cancel` | Отмена пакетной задачи |
| POST | `/api/registration/outlook-batch` | Запуск пакетной регистрации Outlook |
| GET | `/api/registration/outlook-batch/{id}` | Статус пакетной задачи Outlook |
| GET | `/api/registration/tasks` | Список задач |
| GET | `/api/registration/tasks/{uuid}` | Детали задачи |
| GET | `/api/registration/tasks/{uuid}/logs` | Логи задачи |
| POST | `/api/registration/tasks/{uuid}/cancel` | Отмена задачи |
| DELETE | `/api/registration/tasks/{uuid}` | Удаление задачи |
| GET | `/api/registration/available-services` | Доступные почтовые сервисы |
| GET | `/api/registration/outlook-accounts` | Доступные аккаунты Outlook |

### Управление аккаунтами

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/api/accounts` | Список аккаунтов |
| GET | `/api/accounts/{id}` | Детали аккаунта |
| DELETE | `/api/accounts/{id}` | Удаление аккаунта |
| POST | `/api/accounts/batch-delete` | Массовое удаление |
| POST | `/api/accounts/export/json` | Экспорт в JSON |
| POST | `/api/accounts/export/csv` | Экспорт в CSV |
| POST | `/api/accounts/export/cpa` | Экспорт в CPA-формат (файл или ZIP) |
| POST | `/api/accounts/{id}/refresh` | Обновить токен |
| POST | `/api/accounts/batch-refresh` | Массовое обновление токенов |
| POST | `/api/accounts/{id}/validate` | Проверить токен |
| POST | `/api/accounts/batch-validate` | Массовая проверка токенов |
| POST | `/api/accounts/{id}/upload-cpa` | Загрузить в CPA |
| POST | `/api/accounts/batch-upload-cpa` | Массовая загрузка в CPA |

### Оплата и апгрейд

| Метод | Путь | Описание |
|-------|------|----------|
| POST | `/api/payment/generate-link` | Генерация ссылки оплаты Plus/Team |
| POST | `/api/payment/open-incognito` | Открыть браузер в режиме инкогнито |
| POST | `/api/payment/accounts/{id}/mark-subscription` | Отметить тип подписки вручную |
| POST | `/api/payment/accounts/batch-check-subscription` | Массовая проверка подписок |
| POST | `/api/payment/accounts/{id}/upload-tm` | Загрузить аккаунт в Team Manager |
| POST | `/api/payment/accounts/batch-upload-tm` | Массовая загрузка в Team Manager |

### Почтовые сервисы

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/api/email-services` | Список сервисов |
| POST | `/api/email-services` | Добавить сервис |
| GET | `/api/email-services/{id}` | Детали сервиса |
| PATCH | `/api/email-services/{id}` | Обновить сервис |
| DELETE | `/api/email-services/{id}` | Удалить сервис |
| POST | `/api/email-services/{id}/test` | Тестировать сервис |
| POST | `/api/email-services/outlook/batch-import` | Массовый импорт Outlook |

### Настройки

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/api/settings` | Получить все настройки |
| POST | `/api/settings/proxy` | Обновить настройки прокси |
| POST | `/api/settings/dynamic-proxy` | Обновить динамический прокси |
| POST | `/api/settings/cpa` | Обновить настройки CPA |
| POST | `/api/settings/cpa/test` | Тестировать подключение CPA |
| GET/POST | `/api/settings/team-manager` | Настройки Team Manager |
| POST | `/api/settings/team-manager/test` | Тестировать подключение TM |
| GET | `/api/settings/database` | Информация о базе данных |

### WebSocket

| Путь | Описание |
|------|----------|
| `ws://host/api/ws/task/{uuid}` | Логи задачи в реальном времени |
| `ws://host/api/ws/batch/{id}` | Статус и логи пакетной задачи |

## Развёртывание через Docker

### Требования

- Docker
- Docker Compose

### Быстрое развёртывание

```bash
# Клонировать проект
git clone https://github.com/AlterEgo010101/auto-reg-codex.git
cd auto-reg-codex

# Запустить сервис
docker-compose up -d
```

После запуска откройте http://localhost:8000

### Конфигурация

**Проброс портов**: по умолчанию порт `8000`, можно изменить в `docker-compose.yml`.

**Персистентность данных**:
```yaml
volumes:
  - ./data:/app/data
  - ./logs:/app/logs
```

**Настройка прокси**:
```yaml
environment:
  - HTTP_PROXY=http://your-proxy:port
  - HTTPS_PROXY=http://your-proxy:port
```

### Основные команды

```bash
# Просмотр логов
docker-compose logs -f

# Остановка сервиса
docker-compose down

# Пересборка
docker-compose build --no-cache
```

## Примечания

- При первом запуске автоматически создаётся директория `data/` и база данных SQLite
- Все данные аккаунтов и настройки хранятся в `data/database.db`
- Логи записываются в директорию `logs/`
- Приоритет прокси: динамический > список (случайный) > статический по умолчанию
- При регистрации автоматически генерируются имя пользователя и дата рождения (возраст 18–45 лет)
- Загрузка в CPA всегда идёт напрямую, без прокси
- Загрузка в Team Manager всегда идёт напрямую, без прокси
- Генерация ссылок оплаты использует access_token аккаунта, работает через глобальный прокси
- Инкогнито-браузер пробует Chrome, затем Edge; если не найден — возвращает ошибку
- Автоопределение подписки вызывает `chatgpt.com/backend-api/me` через глобальный прокси
- Максимум параллельных регистраций — 50, размер пула потоков соответственно увеличен

## Лицензия

[MIT](LICENSE)
