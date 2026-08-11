"""Телеграм-бот: доставка отобранных постов и команды управления."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from aiogram.filters import Command, CommandObject
from aiogram.types import BotCommand, LinkPreviewOptions, Message

from config import Config
from formatter import human_number, render_digest_header, render_post
from reactions import pattern_label
from storage import Storage

log = logging.getLogger("newsbot.bot")

HELP = """<b>Новостной фильтр по реакциям</b>

/start — подписаться на рассылку
/stop — отписаться
/status — что происходит: каналы, очередь, статистика
/channels — список каналов и их пороги
/digest — прислать всё накопленное прямо сейчас
/top [часов] — топ постов за период (по умолчанию 24 ч), даже если не прошли фильтр
/help — эта справка"""


def make_bot(cfg: Config) -> Bot:
    return Bot(cfg.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))


class Sender:
    """Рассылка карточек подписчикам с уважением к лимитам Telegram."""

    def __init__(self, bot: Bot, store: Storage, cfg: Config):
        self.bot = bot
        self.store = store
        self.cfg = cfg
        self._lock = asyncio.Lock()

    async def _deliver(self, chat_id: int, text: str, link: str | None) -> bool:
        preview = LinkPreviewOptions(is_disabled=True)
        if link:
            preview = LinkPreviewOptions(is_disabled=False, url=link, prefer_small_media=True)

        for attempt in range(3):
            try:
                await self.bot.send_message(chat_id, text, link_preview_options=preview)
                return True
            except TelegramRetryAfter as exc:
                log.warning("Лимит Telegram, ждём %s сек", exc.retry_after)
                await asyncio.sleep(exc.retry_after + 1)
            except TelegramForbiddenError:
                log.warning("Пользователь %s заблокировал бота — снимаем подписку", chat_id)
                await self.store.set_paused(chat_id, True)
                return False
            except Exception:
                log.exception("Не удалось отправить сообщение в чат %s (попытка %s)", chat_id, attempt + 1)
                await asyncio.sleep(2 * (attempt + 1))
        return False

    async def send_posts(self, posts: list[dict[str, Any]], header: str | None = None) -> int:
        """Отправляет пачку постов всем активным подписчикам. Возвращает число отправленных."""
        if not posts:
            return 0

        async with self._lock:
            chats = await self.store.active_subscribers()
            if not chats:
                log.info("Нет активных подписчиков — %s постов ждут в очереди", len(posts))
                return 0

            if header:
                for chat_id in chats:
                    await self._deliver(chat_id, header, None)

            sent = 0
            for post in posts:
                text = render_post(
                    post,
                    preview_chars=self.cfg.delivery.text_preview_chars,
                    tz=self.cfg.delivery.timezone,
                )
                delivered_any = False
                for chat_id in chats:
                    if await self._deliver(chat_id, text, post.get("link")):
                        delivered_any = True
                    await asyncio.sleep(self.cfg.delivery.send_interval_sec)

                if delivered_any:
                    await self.store.mark_sent(post["channel"], post["msg_id"])
                    sent += 1
            return sent

    async def flush_pending(self, header: bool = False) -> int:
        posts = await self.store.pending(self.cfg.delivery.max_per_batch)
        if not posts:
            return 0
        head = render_digest_header(len(posts), self.cfg.delivery.timezone) if header else None
        return await self.send_posts(posts, header=head)


def build_dispatcher(cfg: Config, store: Storage, sender: Sender) -> Dispatcher:
    dp = Dispatcher()

    def allowed(message: Message) -> bool:
        if not cfg.owner_ids:
            return True
        return bool(message.from_user and message.from_user.id in cfg.owner_ids)

    @dp.message(Command("start"))
    async def cmd_start(message: Message) -> None:
        if not allowed(message):
            await message.answer("Бот приватный. Доступ только у владельца.")
            return
        await store.add_subscriber(
            message.chat.id, message.from_user.username if message.from_user else None
        )
        await message.answer(
            f"Подписка включена. Слежу за {len(cfg.channels)} каналами, "
            f"режим доставки: <b>{cfg.delivery.mode}</b>.\n\n{HELP}"
        )

    @dp.message(Command("stop"))
    async def cmd_stop(message: Message) -> None:
        await store.set_paused(message.chat.id, True)
        await message.answer("Рассылка выключена. Вернуть — /start")

    @dp.message(Command("help"))
    async def cmd_help(message: Message) -> None:
        await message.answer(HELP)

    @dp.message(Command("status"))
    async def cmd_status(message: Message) -> None:
        if not allowed(message):
            return
        stats = await store.stats_summary()
        pending = await store.pending_count()
        subscribed = await store.is_subscribed(message.chat.id)
        delivery = cfg.delivery
        schedule = (
            "сразу по мере появления"
            if delivery.mode == "instant"
            else f"дайджест в {', '.join(delivery.digest_times)} ({delivery.timezone})"
        )
        await message.answer(
            "<b>Состояние</b>\n"
            f"Подписка: {'включена' if subscribed else 'выключена'}\n"
            f"Каналов: {len(cfg.channels)}\n"
            f"Доставка: {schedule}\n"
            f"Опрос каналов: раз в {cfg.scan.interval_sec // 60} мин, "
            f"пост оценивается через {cfg.scan.min_age_minutes} мин после публикации\n\n"
            f"Постов в статистике: {stats['total']}\n"
            f"Прошло фильтр: {stats['matched']}\n"
            f"Отправлено: {stats['sent']}\n"
            f"Ждут отправки: {pending}"
        )

    @dp.message(Command("channels"))
    async def cmd_channels(message: Message) -> None:
        if not allowed(message):
            return
        lines = ["<b>Каналы под наблюдением</b>"]
        for ch in cfg.channels:
            flt = ch.filters
            parts = []
            if flt.pattern.enabled and flt.pattern.patterns:
                shown = " или ".join(pattern_label(p) for p in flt.pattern.patterns[:4])
                parts.append(f"порядок реакций {shown}")
            if flt.min_reactions:
                parts.append(f"от {flt.min_reactions} реакций")
            if flt.relative.enabled:
                parts.append(f"×{flt.relative.factor} к медиане")
            if flt.min_engagement_rate:
                parts.append(f"ER ≥ {flt.min_engagement_rate * 100:.1f}%")
            baseline, samples = await store.baseline(ch.key, sample=200)
            stat = f" · медиана {baseline:.0f} по {samples} постам" if samples else ""
            name = ch.title or (f"@{ch.username}" if ch.username else ch.key)
            lines.append(f"• <b>{name}</b> — {', '.join(parts) or 'без порога'}{stat}")
        await message.answer("\n".join(lines))

    @dp.message(Command("digest"))
    async def cmd_digest(message: Message) -> None:
        if not allowed(message):
            return
        count = await sender.flush_pending(header=True)
        if not count:
            await message.answer("Очередь пуста — ничего не набралось выше порога.")

    @dp.message(Command("top"))
    async def cmd_top(message: Message, command: CommandObject) -> None:
        if not allowed(message):
            return
        hours = 24
        if command.args:
            try:
                hours = max(1, min(168, int(command.args.strip().split()[0])))
            except ValueError:
                await message.answer("Формат: /top 12 — топ за 12 часов")
                return

        posts = await store.top(hours, limit=10)
        if not posts:
            await message.answer(f"За {hours} ч данных нет — бот ещё не успел собрать статистику.")
            return

        lines = [f"<b>Топ за {hours} ч</b>"]
        for i, post in enumerate(posts, 1):
            title = post.get("channel_title") or post["channel"]
            link = post.get("link") or ""
            label = f'<a href="{link}">{title}</a>' if link else title
            lines.append(f"{i}. {label} — ❤️ {human_number(int(post['reactions']))}")
        await message.answer("\n".join(lines), link_preview_options=LinkPreviewOptions(is_disabled=True))

    @dp.message(F.text)
    async def fallback(message: Message) -> None:
        if not allowed(message):
            return
        await message.answer(HELP)

    return dp


async def set_commands(bot: Bot) -> None:
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Подписаться"),
            BotCommand(command="status", description="Состояние и статистика"),
            BotCommand(command="channels", description="Каналы и пороги"),
            BotCommand(command="digest", description="Прислать накопленное"),
            BotCommand(command="top", description="Топ постов за период"),
            BotCommand(command="stop", description="Отписаться"),
        ]
    )
