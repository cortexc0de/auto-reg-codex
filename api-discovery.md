# Результаты снифинга OpenAI Workspace API + Abuzovo API

## Дата: 2026-03-19

---

## OpenAI ChatGPT Backend API — Workspace Management

**Base URL**: `https://chatgpt.com/backend-api`
**Auth**: `Authorization: Bearer <access_token>`
**Обязательный заголовок для Team**: `Chatgpt-Account-Id: <account_id>`
**HTTP-клиент**: `curl_cffi` с `impersonate="chrome120"` (обычный curl блокируется Cloudflare)

### Подтверждённые рабочие эндпоинты

#### 1. Информация об аккаунте
```
GET /backend-api/me
```
**Ответ** (ключевые поля):
```json
{
  "id": "user-NHgqyF3tGNxD9MfkW4T4ZZ3B",
  "email": "madarovrinat6@gmail.com",
  "name": "Madarov Rinat",
  "orgs": {
    "data": [
      {
        "id": "org-q5LfE3kuDOkpJ2NXwL7ysSKO",
        "title": "Personal",
        "personal": true,
        "role": "owner",
        "banned": null    // ← поле для детекта бана!
      }
    ]
  },
  "country": "EE"
}
```

#### 2. Полная проверка аккаунтов (подписки, слоты, features)
```
GET /backend-api/accounts/check/v4-2023-04-27
```
**Ответ** (ключевые поля для каждого workspace):
```json
{
  "accounts": {
    "<account_id>": {
      "account": {
        "account_user_role": "standard-user",   // или "account-owner"
        "account_owner_id": "user-oaMMfx...",
        "account_id": "68a1ca0c-...",
        "organization_id": "org-oLmofm...",     // ← org_id workspace'а
        "name": "Sinders",                       // ← имя workspace
        "structure": "workspace",                 // "workspace" = team, "personal" = личный
        "plan_type": "team",                      // "team" / "free" / "plus"
        "is_deactivated": false,                  // ← бан/деактивация!
        "eligible_for_reactivation": true
      },
      "entitlement": {
        "subscription_id": "b01400a3-...",
        "has_active_subscription": true,
        "subscription_plan": "chatgptteamplan",
        "expires_at": "2026-04-12T20:42:27+00:00",  // ← дата истечения
        "renews_at": "2026-04-12T14:42:27+00:00",   // ← дата продления
        "cancels_at": null,                           // ← null = не отменена
        "billing_period": "monthly",
        "is_delinquent": false                        // ← проблема с оплатой?
      },
      "features": ["gpt5", "o3", "o4_mini", "codex_security", ...],
      "last_active_subscription": {
        "will_renew": true
      }
    }
  }
}
```
**Важно**: Один пользователь может быть в НЕСКОЛЬКИХ workspaces. Ответ содержит ВСЕ аккаунты.

#### 3. Список пользователей workspace
```
GET /backend-api/accounts/{account_id}/users
```
**Заголовки**: обязательно `Chatgpt-Account-Id: {account_id}`
**Ответ**:
```json
{
  "items": [
    {
      "id": "user-NHgqyF3tGNxD9MfkW4T4ZZ3B",
      "account_user_id": "user-NHgq...__68a1ca0c-...",
      "email": "madarovrinat6@gmail.com",
      "role": "standard-user",          // "standard-user" | "account-owner"
      "seat_type": "default",
      "name": "Madarov Rinat",
      "created_time": "2026-03-12T19:20:08.115365Z",
      "is_scim_managed": false,
      "deactivated_time": null           // ← если не null — пользователь деактивирован
    }
  ],
  "total": 3,       // ← количество занятых слотов!
  "limit": 50,
  "offset": 0
}
```

#### 4. Список ожидающих приглашений
```
GET /backend-api/accounts/{account_id}/invites
```
**Заголовки**: `Chatgpt-Account-Id: {account_id}`
**Ответ**:
```json
{
  "items": [],     // массив ожидающих приглашений
  "total": 0,
  "limit": 50,
  "offset": 0
}
```

#### 5. Отправить приглашение (WRITE)
```
POST /backend-api/accounts/{account_id}/invites
```
**Тело запроса** (обнаружено через 422 validation):
```json
{
  "email_addresses": ["user@example.com"]
}
```
Может принимать дополнительные поля (role и т.д.) — нужно проверить.

#### 6. Удалить пользователя из workspace — "кик" (WRITE, ОПАСНО!)
```
DELETE /backend-api/accounts/{account_id}/users/{user_id}
```
**Ответ**: `{"success": true}`
**⚠️ ВНИМАНИЕ**: Мгновенно удаляет пользователя и инвалидирует его токен!

#### 7. Настройки workspace
```
GET /backend-api/accounts/{account_id}/settings
```
**Ключевые поля ответа**:
```json
{
  "workspace_id": "68a1ca0c-...",
  "public_display_name": "outlook.com Workspace #91441",
  "allow_external_domain_invites": true,
  "beta_settings": {
    "codex_admin": false,
    "codex_security": true,
    ...
  },
  "share_settings": {
    "gpt_share_setting": "anyone",
    "chat_share_setting": "workspace_only"
  },
  "conversation_ttl": null,
  "seat_type_credit_limits": null    // ← лимиты по типам слотов
}
```

### Проверенные НЕрабочие эндпоинты (404)
- `GET /backend-api/organizations/{org_id}` — 404
- `GET /backend-api/organizations/{org_id}/members` — 404
- `GET /backend-api/organizations/{org_id}/invitations` — 404
- `GET /backend-api/accounts/{account_id}/members` — 404
- `GET /backend-api/accounts/{account_id}/seats` — 404
- `GET /backend-api/accounts/{account_id}/subscription` — 404
- `GET /backend-api/accounts/{account_id}/billing` — 404
- `GET /backend-api/accounts/{account_id}/billing/subscription` — 404
- `GET /backend-api/workspace/{account_id}` — 404
- `GET /backend-api/accounts/{account_id}` — 405 Method Not Allowed

### Как определять ключевые метрики

| Метрика | Как получить |
|---------|-------------|
| **Занятые слоты** | `GET /accounts/{id}/users` → `total` |
| **Макс. слотов** | Из `seat_quantity` при создании Team (по умолчанию 5). Нет прямого API — нужно хранить в нашей БД |
| **Приглашённые** | `GET /accounts/{id}/users` → `items[*].email` + `created_time` |
| **Ожидающие приглашения** | `GET /accounts/{id}/invites` → `items` |
| **Дней до истечения подписки** | `GET /accounts/check/...` → `entitlement.expires_at` - now() |
| **Бан workspace** | `GET /accounts/check/...` → `account.is_deactivated == true` |
| **Бан через email** | Читать почту owner'а через Abuzovo API |
| **Кик пользователя** | `DELETE /accounts/{id}/users/{user_id}` |
| **Пригласить** | `POST /accounts/{id}/invites` → `{"email_addresses": [...]}` |

---

## Abuzovo Email API

**Base URL**: `https://abuzovo-bot.vercel.app`
**Auth**: `Authorization: Bearer <api_token>`

### Подтверждённые эндпоинты

#### 1. Список доменов
```
GET /api/v1/domains
```
**Ответ**:
```json
{
  "domains": [
    {"id": "340338c9-...", "domain": "abuz.store", "is_active": true},
    {"id": "9b776e14-...", "domain": "abuz.online", "is_active": true},
    {"id": "7e3754da-...", "domain": "abuzovo.site", "is_active": true}
  ],
  "prices": {
    "random_email_price": 0.2,
    "custom_email_price": 0.3
  }
}
```

#### 2. Список ящиков
```
GET /api/v1/mailboxes
```
**Ответ**:
```json
{
  "items": [
    {
      "id": "f520b81e-...",
      "user_id": "7ce81033-...",
      "domain_id": "340338c9-...",
      "local_part": "user_hujr2r8",
      "full_address": "user_hujr2r8@abuz.store",
      "type": "random",
      "created_at": "2026-03-19T17:11:23.552701+00:00",
      "owner_label": null,
      "domain": "abuz.store",
      "unread_count": 0,
      "last_message_at": null
    }
  ],
  "total": 1,
  "limit": 10,
  "offset": 0
}
```

#### 3. Создать ящик
```
POST /api/v1/mailboxes
Content-Type: application/json
```
**Тело запроса**:
```json
{
  "domain_id": "340338c9-...",
  "type": "random"
}
```
**Ответ**:
```json
{
  "success": true,
  "email": {
    "id": "f520b81e-...",
    "full_address": "user_hujr2r8@abuz.store",
    "type": "random",
    "domain": "abuz.store",
    "unread_count": 0
  },
  "charged_points": 0.2,
  "mailbox_credentials": {
    "email": "user_hujr2r8@abuz.store",
    "password": "4RVfL_0_0m6ljyuSBb5VOgc-"
  }
}
```
**Примечание**: `type: "custom"` с `local_part` возвращает `"error": "invalid_name"` — формат имени неизвестен. Пока используем только `random`.

#### 4. Удалить ящик
```
DELETE /api/v1/mailboxes
Content-Type: application/json
```
**Тело запроса**:
```json
{
  "mailbox_id": "f520b81e-..."
}
```
**Ответ**: `{"success": true}`

#### 5. Читать письма
```
GET /api/v1/messages?mailbox_id={mailbox_id}
```
**Ответ**:
```json
{
  "items": [],
  "messages": [],
  "total": 0,
  "limit": 10,
  "offset": 0
}
```

#### 6. НЕрабочие
- `GET /api/v1/letters` — 405 Method Not Allowed (нужен mailbox password для делегированного доступа)

### Домены и цены

| Домен | ID | Цена (random) | Цена (custom) |
|-------|-----|---------------|---------------|
| abuz.store | 340338c9-... | 0.2 pts | 0.3 pts |
| abuz.online | 9b776e14-... | 0.2 pts | 0.3 pts |
| abuzovo.site | 7e3754da-... | 0.2 pts | 0.3 pts |

---

## Данные тестового workspace "Sinders"

- **account_id**: `68a1ca0c-f7eb-432f-b811-6fdf9e8801f1`
- **organization_id**: `org-oLmofmfNf9eY4TG1V9y6dFan`
- **owner**: `chromienchaes@outlook.com` (user-oaMMfx6YYClQBTrOFxzRbqU2)
- **plan**: `chatgptteamplan`, monthly
- **subscription**: active until 2026-04-12
- **members** (на момент тестирования):
  - chromienchaes@outlook.com — account-owner
  - mihaylovmark9@gmail.com — standard-user
  - madarovrinat6@gmail.com — standard-user
- **total slots used**: 3
- **is_deactivated**: false (не забанен)

### Второй workspace (деактивирован)
- **account_id**: `f6f6da00-aa68-4205-849f-c42c5380f0f8`
- **name**: "Metz"
- **is_deactivated**: true ← ЗАБАНЕН
- **subscription expired**: 2026-03-04
