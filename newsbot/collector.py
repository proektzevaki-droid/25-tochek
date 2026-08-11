"""Сбор постов из каналов через MTProto и фильтрация по реакциям."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from telethon import TelegramClient
from telethon.errors import ChannelPrivateError, FloodWaitError, UsernameNotOccupiedError
from telethon.tl.types import Message

from config import ChannelConfig, Config, FilterConfig
from reactions import UNKNOWN_MARKER, matches, normalize, pattern_label
from storage import Storage

log = logging.getLogger("newsbot.collector")


@dataclass
class Candidate:
    """Пост канала, приведённый к плоскому виду для фильтра и рендера."""

    channel_key: str
    channel_title: str
    msg_id: int
    ts: int
    text: str
    reactions: int
    views: int
    forwards: int
    breakdown: list[tuple[str, int]]
    ranked: list[str]
    link: str
    is_forward: bool


def _reaction_counts(msg: Message) -> tuple[int, list[tuple[str, int]], list[str]]:
    """Суммарное число реакций, разбивка по эмодзи и рейтинг эмодзи по убыванию.

    В рейтинг (`ranked`) не попадает платная звезда: в интерфейсе Telegram она
    всегда закреплена первой, поэтому «первый смайл» для человека — следующий.
    """
    results = getattr(getattr(msg, "reactions", None), "results", None)
    if not results:
        return 0, [], []

    entries: list[tuple[str, int, bool]] = []
    total = 0
    for item in results:
        count = int(getattr(item, "count", 0) or 0)
        total += count
        is_paid = type(item.reaction).__name__ == "ReactionPaid"
        emoji = getattr(item.reaction, "emoticon", None)
        if emoji is None:
            # Платные и кастомные реакции своего эмодзи не отдают.
            emoji = "⭐" if is_paid else UNKNOWN_MARKER
        entries.append((emoji, count, is_paid))

    # Стабильная сортировка: при равном числе реакций сохраняется порядок Telegram.
    entries.sort(key=lambda entry: entry[1], reverse=True)

    breakdown = [(emoji, count) for emoji, count, _ in entries]
    ranked = [normalize(emoji) for emoji, _, is_paid in entries if not is_paid]
    return total, breakdown, ranked


def _post_link(username: str | None, entity_id: int, msg_id: int) -> str:
    if username:
        return f"https://t.me/{username}/{msg_id}"
    return f"https://t.me/c/{entity_id}/{msg_id}"


def evaluate(cand: Candidate, flt: FilterConfig, baseline: float, samples: int) -> tuple[bool, str]:
    """Проверяет пост против фильтра. Возвращает (прошёл, причина/пояснение)."""
    # Жёсткие отсечки — работают всегда, независимо от mode.
    if flt.skip_forwards and cand.is_forward:
        return False, "репост"
    if flt.min_views and cand.views < flt.min_views:
        return False, f"мало просмотров ({cand.views} < {flt.min_views})"

    text_lc = cand.text.lower()
    if flt.keywords_exclude and any(w in text_lc for w in flt.keywords_exclude):
        return False, "стоп-слово"
    if flt.keywords_include and not any(w in text_lc for w in flt.keywords_include):
        return False, "нет ключевых слов"

    # Условия популярности — объединяются по mode (any / all).
    checks: list[tuple[bool, str]] = []
    gate_notes: list[str] = []

    pat = flt.pattern
    if pat.enabled and pat.patterns:
        hit = next((p for p in pat.patterns if matches(cand.ranked, p, pat.match)), None)
        rating = " ".join(cand.ranked[:4]) or "реакций нет"
        note = f"реакции {rating} по шаблону {pattern_label(hit)}" if hit else f"реакции {rating}"
        if pat.gate:
            # Жёсткое требование: не совпал порядок — пост не берём.
            if hit is None:
                return False, f"порядок реакций не подошёл ({rating})"
            gate_notes.append(note)
        else:
            checks.append((hit is not None, note))

    if flt.min_reactions > 0:
        checks.append(
            (cand.reactions >= flt.min_reactions, f"{cand.reactions} ≥ порога {flt.min_reactions}")
        )

    rel = flt.relative
    if rel.enabled and samples >= rel.min_samples:
        threshold = max(float(rel.floor), baseline * rel.factor)
        checks.append(
            (
                cand.reactions >= threshold,
                f"{cand.reactions} ≥ {threshold:.0f} (медиана канала {baseline:.0f} ×{rel.factor})",
            )
        )

    if flt.min_engagement_rate > 0 and cand.views > 0:
        er = cand.reactions / cand.views
        checks.append(
            (er >= flt.min_engagement_rate, f"вовлечённость {er * 100:.2f}% ≥ {flt.min_engagement_rate * 100:.2f}%")
        )

    if not checks:
        # Остались только жёсткие отсечки — если они пройдены, пост берём.
        return True, "; ".join(gate_notes) or "фильтры популярности выключены"

    passed = [reason for ok, reason in checks if ok]
    if flt.mode == "all" and len(passed) != len(checks):
        return False, "не все условия выполнены"
    if not passed:
        return False, "ниже порога"
    return True, "; ".join(gate_notes + passed)


class Collector:
    def __init__(self, client: TelegramClient, store: Storage, cfg: Config, dry_run: bool = False):
        self.client = client
        self.store = store
        self.cfg = cfg
        self.dry_run = dry_run
        self._entities: dict[str, Any] = {}

    async def _entity(self, ch: ChannelConfig):
        if ch.key not in self._entities:
            self._entities[ch.key] = await self.client.get_entity(ch.ref)
        return self._entities[ch.key]

    async def scan_channel(self, ch: ChannelConfig) -> list[dict[str, Any]]:
        """Опрашивает один канал. Возвращает payload'ы постов, прошедших фильтр."""
        try:
            entity = await self._entity(ch)
        except (ValueError, UsernameNotOccupiedError):
            log.error("Канал %s не найден — проверьте username в config.yaml", ch.key)
            return []
        except ChannelPrivateError:
            log.error("Нет доступа к каналу %s — подпишитесь аккаунтом юзербота", ch.key)
            return []

        title = ch.title or getattr(entity, "title", None) or ch.key
        now = datetime.now(timezone.utc)
        oldest = now - timedelta(hours=self.cfg.scan.max_age_hours)
        ripe_before = now - timedelta(minutes=self.cfg.scan.min_age_minutes)

        messages: list[Message] = []
        try:
            async for msg in self.client.iter_messages(entity, limit=self.cfg.scan.fetch_limit):
                if msg.date < oldest:
                    break
                messages.append(msg)
        except FloodWaitError as exc:
            log.warning("FloodWait %s сек на канале %s", exc.seconds, ch.key)
            await asyncio.sleep(exc.seconds + 1)
            return []

        # Альбом = несколько сообщений с общим grouped_id. Реакции живут на одном
        # из них, текст — обычно на другом. Схлопываем в одну карточку.
        groups: dict[Any, list[Message]] = {}
        for msg in messages:
            key = ("g", msg.grouped_id) if msg.grouped_id else ("m", msg.id)
            groups.setdefault(key, []).append(msg)

        candidates: list[Candidate] = []
        for group in groups.values():
            head = min(group, key=lambda m: m.id)
            if head.date > ripe_before:
                continue  # пост ещё «не настоялся», реакции не набрались

            reactions, breakdown, ranked = max(
                (_reaction_counts(m) for m in group), key=lambda stats: stats[0]
            )
            text = next((m.message for m in group if m.message), "") or ""
            candidates.append(
                Candidate(
                    channel_key=ch.key,
                    channel_title=title,
                    msg_id=head.id,
                    ts=int(head.date.timestamp()),
                    text=text,
                    reactions=reactions,
                    views=max((getattr(m, "views", 0) or 0) for m in group),
                    forwards=max((getattr(m, "forwards", 0) or 0) for m in group),
                    breakdown=breakdown,
                    ranked=ranked,
                    link=_post_link(ch.username, entity.id, head.id),
                    is_forward=head.fwd_from is not None,
                )
            )

        if not candidates:
            return []

        known = await self.store.known_state(ch.key, [c.msg_id for c in candidates])
        baseline, samples = await self.store.baseline(ch.key, sample=200)

        matched: list[dict[str, Any]] = []
        for cand in candidates:
            await self.store.upsert_stats(
                ch.key, cand.msg_id, cand.ts, cand.reactions, cand.views, cand.forwards
            )

            row = known.get(cand.msg_id)
            if row is not None and (row["sent"] or row["matched"]):
                continue  # уже отправлен или уже стоит в очереди

            passed, reason = evaluate(cand, ch.filters, baseline, samples)
            if not passed:
                continue

            payload = {
                "channel_title": cand.channel_title,
                "text": cand.text,
                "link": cand.link,
                "reactions": cand.reactions,
                "views": cand.views,
                "forwards": cand.forwards,
                "breakdown": cand.breakdown,
                "ranked": cand.ranked,
                "ts": cand.ts,
                "reason": reason,
            }
            if not self.dry_run:
                await self.store.mark_matched(ch.key, cand.msg_id, payload)
            matched.append({"channel": ch.key, "msg_id": cand.msg_id, **payload})
            log.info("✅ %s/%s — %s реакций (%s)", ch.key, cand.msg_id, cand.reactions, reason)

        return matched

    async def scan_all(self) -> list[dict[str, Any]]:
        started = time.monotonic()
        found: list[dict[str, Any]] = []
        for i, ch in enumerate(self.cfg.channels):
            try:
                found.extend(await self.scan_channel(ch))
            except FloodWaitError as exc:
                log.warning("FloodWait %s сек, пауза", exc.seconds)
                await asyncio.sleep(exc.seconds + 1)
            except Exception:
                log.exception("Ошибка при обходе канала %s", ch.key)
            if i < len(self.cfg.channels) - 1:
                await asyncio.sleep(self.cfg.scan.pause_between_channels_sec)

        log.info(
            "Обход %s каналов завершён за %.1f сек, отобрано постов: %s",
            len(self.cfg.channels),
            time.monotonic() - started,
            len(found),
        )
        return found
