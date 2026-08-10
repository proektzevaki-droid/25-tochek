"""Точка входа: юзербот читает каналы, бот доставляет отфильтрованное."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

from telethon import TelegramClient

from bot import Sender, build_dispatcher, make_bot, set_commands
from collector import Collector
from config import Config, ConfigError, load_config
from formatter import render_post
from storage import Storage

log = logging.getLogger("newsbot")

CLEANUP_KEEP_DAYS = 30


def setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%d.%m %H:%M:%S",
    )
    logging.getLogger("telethon").setLevel(logging.WARNING)
    logging.getLogger("aiogram.event").setLevel(logging.WARNING)


async def make_userbot(cfg: Config) -> TelegramClient:
    """Поднимает клиент юзербота из уже созданной сессии."""
    client = TelegramClient(str(cfg.session_path), cfg.api_id, cfg.api_hash)
    await client.connect()
    if not await client.is_user_authorized():
        await client.disconnect()
        raise ConfigError(
            f"Сессия {cfg.session_path.name} не авторизована. "
            "Запустите один раз: python login.py"
        )
    me = await client.get_me()
    log.info("Юзербот подключён: %s (id %s)", getattr(me, "username", None) or me.first_name, me.id)
    return client


async def scan_loop(collector: Collector, sender: Sender, cfg: Config) -> None:
    while True:
        try:
            found = await collector.scan_all()
            if found and cfg.delivery.mode == "instant":
                await sender.flush_pending(header=False)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Сбой цикла сканирования — продолжаем через %s сек", cfg.scan.interval_sec)
        await asyncio.sleep(cfg.scan.interval_sec)


async def digest_loop(sender: Sender, store: Storage, cfg: Config) -> None:
    """Раз в 30 сек проверяет, не наступило ли время дайджеста."""
    tz = ZoneInfo(cfg.delivery.timezone)
    while True:
        try:
            now = datetime.now(tz)
            today = now.strftime("%Y-%m-%d")
            for slot in cfg.delivery.digest_times:
                hh, mm = (int(x) for x in slot.split(":"))
                due = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
                if now < due:
                    continue
                key = f"digest_last:{slot}"
                if await store.get_meta(key) == today:
                    continue
                await store.set_meta(key, today)
                count = await sender.flush_pending(header=True)
                log.info("Дайджест %s: отправлено постов — %s", slot, count)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Сбой планировщика дайджеста")
        await asyncio.sleep(30)


async def cleanup_loop(store: Storage) -> None:
    while True:
        await asyncio.sleep(24 * 3600)
        try:
            removed = await store.cleanup(CLEANUP_KEEP_DAYS)
            log.info("Очистка статистики: удалено записей — %s", removed)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Сбой очистки БД")


async def run(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    store = Storage(cfg.db_path)
    await store.init()

    client = await make_userbot(cfg)
    collector = Collector(client, store, cfg, dry_run=args.dry_run)

    try:
        if args.dry_run or args.once:
            found = await collector.scan_all()
            if args.dry_run:
                print(f"\n=== Прошли фильтр: {len(found)} ===\n")
                for post in found:
                    print(render_post(post, cfg.delivery.text_preview_chars, cfg.delivery.timezone))
                    print(f"[причина: {post.get('reason')}]\n{'-' * 60}")
                return 0

            bot = make_bot(cfg)
            try:
                sent = await Sender(bot, store, cfg).flush_pending(header=cfg.delivery.mode == "digest")
                log.info("Разовый прогон: отобрано %s, отправлено %s", len(found), sent)
            finally:
                await bot.session.close()
            return 0

        bot = make_bot(cfg)
        sender = Sender(bot, store, cfg)
        dp = build_dispatcher(cfg, store, sender)
        await set_commands(bot)

        log.info(
            "Старт: каналов %s, режим доставки %s, опрос раз в %s сек",
            len(cfg.channels),
            cfg.delivery.mode,
            cfg.scan.interval_sec,
        )

        tasks = [
            asyncio.create_task(scan_loop(collector, sender, cfg), name="scan"),
            asyncio.create_task(cleanup_loop(store), name="cleanup"),
            asyncio.create_task(dp.start_polling(bot, handle_signals=False), name="polling"),
        ]
        if cfg.delivery.mode == "digest":
            tasks.append(asyncio.create_task(digest_loop(sender, store, cfg), name="digest"))

        try:
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            for task in done:
                if task.exception():
                    raise task.exception()  # type: ignore[misc]
        finally:
            await dp.storage.close()
            await bot.session.close()
        return 0
    finally:
        await client.disconnect()
        await store.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Новостной фильтр Telegram-каналов по реакциям")
    parser.add_argument("-c", "--config", help="путь к config.yaml")
    parser.add_argument("--once", action="store_true", help="один цикл сканирования и выход")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="показать, что прошло бы фильтр, ничего не отправляя (для подбора порогов)",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="подробные логи")
    args = parser.parse_args()

    setup_logging(args.verbose)
    try:
        return asyncio.run(run(args))
    except ConfigError as exc:
        log.error("%s", exc)
        return 1
    except KeyboardInterrupt:
        log.info("Остановлено пользователем")
        return 0


if __name__ == "__main__":
    sys.exit(main())
