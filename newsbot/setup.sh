#!/usr/bin/env bash
#
# Мастер установки: спрашивает ключи, настраивает всё сам и показывает,
# что прошло бы фильтр за сутки. Запускать НА СЕРВЕРЕ из папки newsbot/
# внутри репозитория:
#
#     cd /home/devartemiy/25tochek/Dashborad/newsbot && bash setup.sh
#
# Повторный запуск безопасен: уже введённые ключи и готовая сессия
# не трогаются, шаги пропускаются.

set -euo pipefail

TARGET="${TARGET:-$HOME/newsbot}"
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

step() { printf '\n\033[1;36m═══ %s\033[0m\n' "$1"; }
ok()   { printf '\033[32m  ✓ %s\033[0m\n' "$1"; }
warn() { printf '\033[33m  ! %s\033[0m\n' "$1"; }

# ── 1. Установка ─────────────────────────────────────────────────────────────
step "Шаг 1 из 4. Установка"
TARGET="$TARGET" bash "$SRC/deploy.sh" >/dev/null
ok "код, окружение и зависимости на месте: $TARGET"

ENV_FILE="$TARGET/.env"
CONFIG="$TARGET/config.yaml"
PY="$TARGET/venv/bin/python"

env_value() { sed -n "s/^$1=//p" "$ENV_FILE" 2>/dev/null | tail -1; }

env_set() {
  local key="$1" value="$2"
  if grep -q "^$key=" "$ENV_FILE" 2>/dev/null; then
    # Значение подставляем через переменную окружения, чтобы спецсимволы
    # в ключах не сломали sed.
    KEY="$key" VALUE="$value" "$PY" - "$ENV_FILE" <<'PY'
import os, sys, pathlib
path = pathlib.Path(sys.argv[1])
key, value = os.environ["KEY"], os.environ["VALUE"]
lines = path.read_text(encoding="utf-8").splitlines()
out = [f"{key}={value}" if line.startswith(f"{key}=") else line for line in lines]
path.write_text("\n".join(out) + "\n", encoding="utf-8")
PY
  else
    printf '%s=%s\n' "$key" "$value" >> "$ENV_FILE"
  fi
}

# ── 2. Ключи ─────────────────────────────────────────────────────────────────
step "Шаг 2 из 4. Ключи"

if [[ "$(env_value TG_API_ID)" =~ ^[0-9]+$ ]]; then
  ok "TG_API_ID уже задан"
else
  echo "  api_id и api_hash берутся на https://my.telegram.org"
  echo "  → войти по номеру телефона → API development tools"
  echo
  while :; do
    read -r -p "  api_id (число): " API_ID
    [[ "$API_ID" =~ ^[0-9]+$ ]] && break
    warn "нужно число"
  done
  read -r -p "  api_hash: " API_HASH
  env_set TG_API_ID "$API_ID"
  env_set TG_API_HASH "$API_HASH"
  ok "записаны в .env"
fi

if [[ -n "$(env_value BOT_TOKEN)" && "$(env_value BOT_TOKEN)" != *AAxxxx* ]]; then
  ok "BOT_TOKEN уже задан"
else
  echo
  echo "  Токен бота берётся у @BotFather: команда /newbot"
  # Ввод скрытый: токен не останется в истории терминала и в логах сессии.
  read -r -s -p "  токен бота (ввод скрыт): " BOT_TOKEN
  echo
  env_set BOT_TOKEN "$BOT_TOKEN"
  ok "записан в .env"
fi

chmod 600 "$ENV_FILE"

# ── 3. Вход в аккаунт ────────────────────────────────────────────────────────
step "Шаг 3 из 4. Вход в аккаунт-читатель"

if OWNER_ID="$(cd "$TARGET" && "$PY" login.py --whoami 2>/dev/null)"; then
  ok "аккаунт уже авторизован, user_id $OWNER_ID"
else
  echo "  Сейчас спросит номер телефона и код из Telegram."
  echo "  Это ваш обычный аккаунт — он будет только читать каналы."
  echo
  (cd "$TARGET" && "$PY" login.py)
  OWNER_ID="$(cd "$TARGET" && "$PY" login.py --whoami)"
fi

# owner_ids закрывает бота от посторонних: команды примет только владелец.
if grep -qE '^owner_ids:\s*\[\s*\]' "$CONFIG"; then
  OWNER="$OWNER_ID" "$PY" - "$CONFIG" <<'PY'
import os, re, sys, pathlib
path = pathlib.Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
path.write_text(
    re.sub(r"^owner_ids:\s*\[\s*\]", f"owner_ids: [{os.environ['OWNER']}]", text, count=1, flags=re.M),
    encoding="utf-8",
)
PY
  ok "owner_ids: [$OWNER_ID] — бот будет слушаться только вас"
else
  ok "owner_ids уже заполнен"
fi

# ── 4. Проверка правил ───────────────────────────────────────────────────────
step "Шаг 4 из 4. Что прошло бы фильтр за сутки"
echo "  Ничего не отправляется — только показывается на экране."
echo

REPORT="$TARGET/dry-run.txt"
set +e
(cd "$TARGET" && "$PY" main.py --dry-run 2>&1) | tee "$REPORT"
STATUS=${PIPESTATUS[0]}
set -e

echo
if [[ $STATUS -ne 0 ]]; then
  warn "проверка завершилась с ошибкой — покажите вывод выше"
  exit $STATUS
fi

cat <<FINAL

════════════════════════════════════════════════════════════════
Всё настроено. Вывод сохранён в $REPORT

Если список выглядит правильно — запускаем бота насовсем:

    sudo systemctl enable --now newsbot
    sudo journalctl -u newsbot -f

Потом напишите своему боту /start — начнёт присылать новости.

Если в списке лишнее или чего-то не хватает — покажите
$REPORT, поправим правила.
════════════════════════════════════════════════════════════════
FINAL
