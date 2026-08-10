#!/usr/bin/env bash
#
# Разворачивает newsbot на сервере. Запускать НА СЕРВЕРЕ из папки newsbot/
# внутри репозитория:
#
#     cd /home/devartemiy/25tochek/Dashborad/newsbot && bash deploy.sh
#
# Скрипт идемпотентный: existing .env, config.yaml, база и сессия не трогаются.
# Ничего не запускает — сервис поднимается вручную после авторизации аккаунта.

set -euo pipefail

TARGET="${TARGET:-$HOME/newsbot}"
SERVICE="${SERVICE:-newsbot}"
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

say() { printf '\n\033[1m▸ %s\033[0m\n' "$1"; }
warn() { printf '\033[33m  ! %s\033[0m\n' "$1"; }

if [[ "$SRC" == "$TARGET" ]]; then
  echo "Ошибка: запускать нужно из репозитория, а не из $TARGET" >&2
  exit 1
fi

say "Целевая папка: $TARGET"
mkdir -p "$TARGET"

say "Копирую код"
# Только код. Секреты, база и сессия остаются на месте.
for f in main.py collector.py config.py storage.py bot.py formatter.py \
         reactions.py login.py test_filter.py requirements.txt \
         config.example.yaml .env.example .gitignore README.md; do
  cp "$SRC/$f" "$TARGET/$f"
done
echo "  скопировано файлов: 15"

say "Виртуальное окружение"
if [[ ! -d "$TARGET/venv" ]]; then
  python3 -m venv "$TARGET/venv"
  echo "  создано"
else
  echo "  уже есть"
fi
"$TARGET/venv/bin/pip" install --quiet --upgrade pip setuptools wheel
"$TARGET/venv/bin/pip" install --quiet -r "$TARGET/requirements.txt"
echo "  зависимости установлены: $("$TARGET/venv/bin/python" -c 'import telethon,aiogram; print("telethon",telethon.__version__,"/ aiogram",aiogram.__version__)')"

say "Конфигурация"
if [[ ! -f "$TARGET/.env" ]]; then
  cp "$TARGET/.env.example" "$TARGET/.env"
  warn "создан $TARGET/.env — впишите TG_API_ID, TG_API_HASH, BOT_TOKEN"
else
  echo "  .env на месте, не трогаю"
fi
if [[ ! -f "$TARGET/config.yaml" ]]; then
  cp "$TARGET/config.example.yaml" "$TARGET/config.yaml"
  warn "создан $TARGET/config.yaml — проверьте список каналов и owner_ids"
else
  echo "  config.yaml на месте, не трогаю"
fi

say "Права на секреты"
# Файл сессии равнозначен доступу к аккаунту — закрываем от других пользователей.
chmod 700 "$TARGET"
chmod 600 "$TARGET/.env" 2>/dev/null || true
chmod 600 "$TARGET"/*.session 2>/dev/null || true
echo "  папка 700, .env и сессия 600"

say "Тесты фильтра"
(cd "$TARGET" && ./venv/bin/python test_filter.py | tail -1)

say "systemd-юнит"
UNIT="/etc/systemd/system/${SERVICE}.service"
TMP_UNIT="$(mktemp)"
cat > "$TMP_UNIT" <<UNITEOF
[Unit]
Description=Telegram newsbot — фильтр новостей по реакциям
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$(id -un)
WorkingDirectory=$TARGET
ExecStart=$TARGET/venv/bin/python main.py
Restart=always
RestartSec=15
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
UNITEOF

cp "$TMP_UNIT" "$TARGET/${SERVICE}.service"
if sudo -n true 2>/dev/null && sudo cp "$TMP_UNIT" "$UNIT" 2>/dev/null; then
  if sudo systemctl daemon-reload 2>/dev/null; then
    echo "  юнит установлен: $UNIT"
  else
    warn "юнит скопирован, но systemctl daemon-reload не отработал — выполните вручную"
  fi
else
  warn "нет sudo без пароля. Юнит подготовлен: $TARGET/${SERVICE}.service"
  warn "установите вручную:  sudo cp $TARGET/${SERVICE}.service $UNIT && sudo systemctl daemon-reload"
fi
rm -f "$TMP_UNIT"

cat <<FINAL

════════════════════════════════════════════════════════════════
Установка закончена. Сервис НЕ запущен — осталось три шага:

  1. nano $TARGET/.env
     TG_API_ID и TG_API_HASH — с https://my.telegram.org
     BOT_TOKEN — от @BotFather

  2. cd $TARGET && ./venv/bin/python login.py
     Спросит телефон, код из Telegram и пароль 2FA.
     Покажет ваш user_id — впишите его в owner_ids в config.yaml.

  3. cd $TARGET && ./venv/bin/python main.py --dry-run
     Покажет, что прошло бы фильтр за сутки. Ничего не отправляет.

Когда результат устроит:

     sudo systemctl enable --now $SERVICE
     sudo journalctl -u $SERVICE -f
════════════════════════════════════════════════════════════════
FINAL
