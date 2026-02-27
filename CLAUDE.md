# Проект: Заказы с 25 точек

## Суть
Автоматизация приёма заказов от 25 торговых точек через Telegram-бот → n8n (Whisper + GPT-4) → FastAPI дашборд → Excel → отправка поставщикам (Telegram/Email).

## Статус
- **В продакшене** с января 2026
- С системой работают операторы ежедневно
- **ПРАВИЛО:** не ломать рабочую систему. Бэкап перед любыми изменениями.

## Архитектура

```
Точка (Telegram) → n8n (Whisper+GPT-4) → FastAPI API → SQLite
                                                ↓
                                          Дашборд (оператор)
                                                ↓
                                    Excel → Поставщики (Telegram/Email)
```

| Компонент | Технология | URL/Расположение |
|-----------|-----------|-----------------|
| Backend | Python FastAPI + Uvicorn | http://77.73.232.184:12000 |
| БД | SQLite (app.db) | /home/devartemiy/25tochek/Dashborad/app.db |
| n8n | Self-hosted | https://egorov-n8n.store |
| Frontend | Vanilla HTML/JS/CSS (Jinja2) | /dashboard |
| Сервис | systemd fastapi-dashboard | /etc/systemd/system/fastapi-dashboard.service |

## Ключевые ID и доступы

| Ресурс | Значение |
|--------|----------|
| Сервер | 77.73.232.184, порт 12000 |
| SSH | порт 22 (пользователь — уточнить) |
| GitHub | proektzevaki-droid/25-tochek |
| n8n | https://egorov-n8n.store |
| Webhook отправки | /webhook/5612c781-47d6-48ae-add7-3e862c33407a |
| Telegram credential | wu7zBuTexsZhK9BB |
| Google credential | O4tyXN5dH31VB3Wd |
| SMTP | smtp.mail.ru, mysinvl2009@mail.ru |

## База данных (SQLite, 9 таблиц)

| Таблица | Назначение | Ключевые поля |
|---------|-----------|---------------|
| points | Торговые точки (~25) | name, idTg, owner, is_deleted |
| orders | Заказы | point_id, status (new/confirmed/rejected), sent_to_supplier |
| order_items | Позиции заказов | order_id, product_id, suppliers_id, type, name, count |
| product | Товары (11 типов) | name, unit, product_type |
| suppliers | Поставщики | name, email, telegram, telegram_id |
| supplier_products | Связь поставщик↔товар | supplier_id, product_id (UNIQUE) |
| supplier_rules | Правила выбора поставщиков | supplier_id, rule_text, priority |
| history | История отправок | file_path, status, order_id, supplier_id |
| history_order_items | Связь история↔позиции | history_id, order_item_id (UNIQUE) |

## API Endpoints (основные)

```
# Заказы
POST   /orders                     — создание (из n8n)
GET    /orders?status=...          — список
PATCH  /orders/{id}/status         — смена статуса
PATCH  /order-items/update-count   — UPSERT количества

# Выгрузка
GET    /export/by-type?type=...    — по типу товара
GET    /export/pack                — Упаковка
GET    /export/limonad             — Лимонады
GET    /orders/pending-supplier    — для отправки

# Отправка поставщикам
POST   /send/supplier-telegram     — через Telegram
POST   /send/supplier-email        — через Email
POST   /send/supplier-telegram/callback — callback подтверждения

# Справочники
GET/POST/PATCH/DELETE  /points, /products, /suppliers
```

## n8n Workflows

| Workflow | Файл | Назначение |
|----------|------|-----------|
| Приём заказов | n8n_workflow_zakazy_25_tochek.json | Telegram → Whisper → GPT-4 → Google Sheets → POST /orders |
| Отправка поставщикам | n8n_workflow_otpravka_zayavok.json | Webhook → Telegram бот → Callback |

## Сервис (systemd)

```bash
# Управление
sudo systemctl start/stop/restart fastapi-dashboard
sudo systemctl status fastapi-dashboard

# Логи
sudo journalctl -u fastapi-dashboard -f          # реал-тайм
sudo journalctl -u fastapi-dashboard -n 100       # последние 100
sudo journalctl -u fastapi-dashboard | grep ERROR  # ошибки
sudo journalctl -u fastapi-dashboard | grep "ДУБЛЬ" # дубли
```

## Бэкапы

```bash
# Создание (ОБЯЗАТЕЛЬНО перед любыми изменениями!)
cd /home/devartemiy/25tochek/Dashborad
tar -czf "../backups/$(date +%Y-%m-%d)_описание.tar.gz" \
  main.py models.py database.py schemas.py app.db .env \
  requirements.txt fill_template.py generate_template.py \
  static/ templates/ alembic/ alembic.ini

# Восстановление
tar -xzf ../backups/ФАЙЛ.tar.gz
sudo systemctl restart fastapi-dashboard
```

## SSH правила

- Макс 3-5 SSH подключений подряд, потом пауза 30 сек
- Паттерн "один скрипт": подготовить всё локально → scp → ssh "bash script.sh"
- Никогда 20+ подключений (инцидент из проекта "Накладные" — Load Average 66)

## Принципы работы

1. **Не ломать рабочую систему** — она в продакшене, люди работают
2. **Бэкап перед изменениями** — tar + git commit
3. **Тестовая ветка** — feature/* для разработки, main для стабильной версии
4. **Не создавать тестовые записи** в боевой БД без явного разрешения
5. **Коммит = milestone** — только после подтверждения пользователем
6. **Правило 2 попытки** — после 2 неудач СТОП, предложить варианты

## Защита (уже реализовано)

- Rate limiting: 5 запросов/сек на POST /orders
- Дедупликация заказов: 60 сек окно
- Soft delete для точек
- SQLAlchemy защита от SQL injection
- .gitignore: .env, app.db, venv/, exports/

## Известные проблемы / технический долг

- [ ] README на транслите — нужно обновить на русский
- [ ] dashboard.html — 3451 строка, монолит
- [ ] Нет Error Handler workflow в n8n
- [ ] Нет мониторинга (по опыту "Актов" — нужен Schedule каждые 5 мин)
- [ ] is_closed в orders не используется
- [ ] Credentials хардкод — нет разделения prod/dev

## Типы товаров (11)

Белизна, Вафельное полотно, Вода, Ирексол софт сдоба, Лимонады, Молочка, Мука/Сахар, Пищеснаб, Продукты, Сосиски, Упаковка
