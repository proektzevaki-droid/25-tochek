# 25 точек — Система управления заказами

## Описание

Автоматизированная система приёма и обработки заказов от 25 торговых точек. Заказы поступают через Telegram-бот (голос/текст), распознаются AI и попадают в дашборд для обработки оператором.

### Компоненты

- **FastAPI Dashboard** — веб-интерфейс для управления заказами, точками, поставщиками
- **Telegram Bot** — приём заказов от операторов точек
- **n8n Workflows** — оркестрация (Whisper + GPT-4 + Google Sheets)
- **SQLite Database** — хранение данных (9 таблиц)

### Технологии

- Python 3.x + FastAPI + Uvicorn
- SQLAlchemy ORM + SQLite + Alembic
- OpenAI Whisper (голос → текст) + GPT-4 (текст → JSON)
- n8n (автоматизация workflows)
- Telegram Bot API + SMTP (mail.ru)
- OpenPyXL (генерация Excel)

### Бизнес-процесс

```
Точка (Telegram) → n8n (AI) → Дашборд (оператор) → Excel → Поставщики
```

## Статус

- В продакшене с января 2026
- Сервер: 77.73.232.184:12000
- Дашборд: http://77.73.232.184:12000/dashboard

## Структура

```
├── main.py                    # FastAPI приложение (127 KB)
├── models.py                  # SQLAlchemy модели (9 таблиц)
├── database.py                # Подключение к SQLite
├── schemas.py                 # Pydantic схемы
├── fill_template.py           # Заполнение Excel шаблонов
├── generate_template.py       # Генерация Excel шаблонов
├── templates/dashboard.html   # Frontend (Jinja2)
├── static/css/, static/js/    # Стили и скрипты
├── alembic/                   # Миграции БД
├── n8n_workflow_*.json        # n8n workflows
├── CLAUDE.md                  # Правила для Claude Code
├── КАРТОЧКА_ПРОЕКТА.txt       # Карточка проекта
└── документация/              # Полная техническая документация
```

## Бэкапы

```bash
# Создание (на сервере)
cd /home/devartemiy/25tochek/Dashborad
tar -czf "../backups/$(date +%Y-%m-%d)_описание.tar.gz" \
  main.py models.py database.py schemas.py app.db .env \
  requirements.txt fill_template.py generate_template.py \
  static/ templates/ alembic/ alembic.ini
```

## GitHub

Репозиторий: https://github.com/proektzevaki-droid/25-tochek
