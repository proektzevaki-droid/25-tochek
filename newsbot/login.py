"""Разовый вход в аккаунт-читатель + помощник по заполнению списка каналов.

    python login.py            — авторизация, создаёт файл сессии
    python login.py --list     — выводит каналы, на которые подписан аккаунт,
                                 готовым куском YAML для config.yaml
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.tl.types import Channel

BASE_DIR = Path(__file__).resolve().parent


async def whoami(session_path: Path, api_id: int, api_hash: str) -> int:
    """Печатает только user_id уже авторизованного аккаунта. Ничего не спрашивает."""
    client = TelegramClient(str(session_path), api_id, api_hash)
    await client.connect()
    if not await client.is_user_authorized():
        await client.disconnect()
        print("Сессия не авторизована", file=sys.stderr)
        return 1
    me = await client.get_me()
    print(me.id)
    await client.disconnect()
    return 0


async def run(list_channels: bool, session: str) -> int:
    load_dotenv(BASE_DIR / ".env")
    api_id = os.getenv("TG_API_ID", "").strip()
    api_hash = os.getenv("TG_API_HASH", "").strip()
    if not api_id.isdigit() or not api_hash:
        print("Заполните TG_API_ID и TG_API_HASH в .env (см. .env.example)", file=sys.stderr)
        return 1

    session_path = Path(session)
    if not session_path.is_absolute():
        session_path = BASE_DIR / session_path

    client = TelegramClient(str(session_path), int(api_id), api_hash)
    await client.start(password=lambda: os.getenv("TG_PASSWORD") or input("Пароль 2FA: "))

    me = await client.get_me()
    print(f"\n✅ Готово. Вошли как {me.first_name} (@{me.username}), id {me.id}")
    print(f"   Сессия: {session_path}")
    print(f"   Ваш user_id для owner_ids в config.yaml: {me.id}\n")

    if list_channels:
        print("channels:")
        async for dialog in client.iter_dialogs():
            entity = dialog.entity
            if not isinstance(entity, Channel) or not entity.broadcast:
                continue  # нужны только каналы, не группы
            title = (entity.title or "").replace('"', "'")
            if entity.username:
                print(f'  - username: "{entity.username}"')
            else:
                print(f"  - id: {dialog.id}")
            print(f'    title: "{title}"')

    await client.disconnect()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Авторизация аккаунта-читателя")
    parser.add_argument("--list", action="store_true", help="вывести каналы в формате config.yaml")
    parser.add_argument("--whoami", action="store_true", help="напечатать user_id и выйти")
    parser.add_argument("--session", default="newsbot.session", help="путь к файлу сессии")
    args = parser.parse_args()

    if args.whoami:
        load_dotenv(BASE_DIR / ".env")
        api_id = os.getenv("TG_API_ID", "").strip()
        api_hash = os.getenv("TG_API_HASH", "").strip()
        if not api_id.isdigit() or not api_hash:
            print("Не заданы TG_API_ID / TG_API_HASH", file=sys.stderr)
            return 1
        session_path = Path(args.session)
        if not session_path.is_absolute():
            session_path = BASE_DIR / session_path
        return asyncio.run(whoami(session_path, int(api_id), api_hash))

    return asyncio.run(run(args.list, args.session))


if __name__ == "__main__":
    sys.exit(main())
