"""Сборка HTML-карточки поста для отправки в Telegram."""

from __future__ import annotations

import html
import re
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

_WHITESPACE = re.compile(r"\n{3,}")


def human_number(value: int) -> str:
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M".replace(".0M", "M")
    if value >= 1_000:
        return f"{value / 1_000:.1f}K".replace(".0K", "K")
    return str(value)


def _preview(text: str, limit: int) -> str:
    text = _WHITESPACE.sub("\n\n", (text or "").strip())
    if not text:
        return ""
    if len(text) <= limit:
        return text
    cut = text[:limit]
    # Стараемся обрезать по границе предложения или слова, а не посреди буквы.
    for sep in (". ", "! ", "? ", "\n", " "):
        idx = cut.rfind(sep)
        if idx > limit * 0.6:
            cut = cut[: idx + 1]
            break
    return cut.rstrip() + "…"


def render_post(payload: dict[str, Any], preview_chars: int = 350, tz: str = "Europe/Moscow") -> str:
    """Одна карточка: канал, метрики, отрывок текста, ссылка на оригинал."""
    title = html.escape(str(payload.get("channel_title") or payload.get("channel") or "Канал"))
    reactions = int(payload.get("reactions") or 0)
    views = int(payload.get("views") or 0)
    link = payload.get("link") or ""

    breakdown = payload.get("breakdown") or []
    top = " ".join(f"{html.escape(str(emoji))}{human_number(int(count))}" for emoji, count in breakdown[:4])

    metrics = [f"{human_number(reactions)} реакций"]
    if views:
        metrics.append(f"👁 {human_number(views)}")
    try:
        when = datetime.fromtimestamp(int(payload["ts"]), ZoneInfo(tz))
        metrics.append(when.strftime("%d.%m %H:%M"))
    except (KeyError, TypeError, ValueError):
        pass

    lines = [f"🔥 <b>{title}</b>", "  ·  ".join(metrics)]
    if top:
        lines.append(top)

    body = _preview(str(payload.get("text") or ""), preview_chars)
    if body:
        lines.append("")
        lines.append(html.escape(body))

    if link:
        lines.append("")
        lines.append(f'<a href="{html.escape(link, quote=True)}">Открыть пост</a>')

    return "\n".join(lines)


def render_digest_header(count: int, tz: str = "Europe/Moscow") -> str:
    now = datetime.now(ZoneInfo(tz)).strftime("%d.%m %H:%M")
    word = "пост" if count % 10 == 1 and count % 100 != 11 else (
        "поста" if count % 10 in (2, 3, 4) and count % 100 not in (12, 13, 14) else "постов"
    )
    return f"📰 <b>Дайджест {now}</b>\nОтобрано {count} {word} по реакциям."
