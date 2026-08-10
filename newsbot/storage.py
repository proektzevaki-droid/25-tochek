"""Хранилище состояния: статистика постов, очередь на отправку, подписчики."""

from __future__ import annotations

import json
import time
from pathlib import Path
from statistics import median
from typing import Any

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS posts (
    channel   TEXT    NOT NULL,
    msg_id    INTEGER NOT NULL,
    ts        INTEGER NOT NULL,          -- дата поста, unixtime
    reactions INTEGER NOT NULL DEFAULT 0,
    views     INTEGER NOT NULL DEFAULT 0,
    forwards  INTEGER NOT NULL DEFAULT 0,
    matched   INTEGER NOT NULL DEFAULT 0, -- прошёл фильтр
    sent      INTEGER NOT NULL DEFAULT 0, -- уже отправлен подписчикам
    sent_ts   INTEGER,
    payload   TEXT,                       -- JSON с данными для рендера
    PRIMARY KEY (channel, msg_id)
);

CREATE INDEX IF NOT EXISTS idx_posts_pending ON posts (matched, sent, ts);
CREATE INDEX IF NOT EXISTS idx_posts_channel_ts ON posts (channel, ts DESC);

CREATE TABLE IF NOT EXISTS subscribers (
    chat_id  INTEGER PRIMARY KEY,
    username TEXT,
    added_ts INTEGER NOT NULL,
    paused   INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


class Storage:
    def __init__(self, path: Path):
        self.path = path
        self._db: aiosqlite.Connection | None = None

    async def init(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self.path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.executescript(SCHEMA)
        await self._db.commit()

    async def close(self) -> None:
        if self._db is not None:
            await self._db.close()
            self._db = None

    @property
    def db(self) -> aiosqlite.Connection:
        if self._db is None:
            raise RuntimeError("Storage.init() не был вызван")
        return self._db

    # ── Посты ────────────────────────────────────────────────────────────────

    async def known_state(self, channel: str, msg_ids: list[int]) -> dict[int, aiosqlite.Row]:
        """Возвращает уже сохранённые записи по списку id (чтобы не слать дважды)."""
        if not msg_ids:
            return {}
        placeholders = ",".join("?" * len(msg_ids))
        cur = await self.db.execute(
            f"SELECT * FROM posts WHERE channel = ? AND msg_id IN ({placeholders})",
            [channel, *msg_ids],
        )
        rows = await cur.fetchall()
        return {row["msg_id"]: row for row in rows}

    async def upsert_stats(
        self, channel: str, msg_id: int, ts: int, reactions: int, views: int, forwards: int
    ) -> None:
        """Сохраняет/обновляет метрики поста, не трогая флаги matched/sent."""
        await self.db.execute(
            """
            INSERT INTO posts (channel, msg_id, ts, reactions, views, forwards)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT (channel, msg_id) DO UPDATE SET
                reactions = excluded.reactions,
                views     = excluded.views,
                forwards  = excluded.forwards
            """,
            (channel, msg_id, ts, reactions, views, forwards),
        )
        await self.db.commit()

    async def mark_matched(self, channel: str, msg_id: int, payload: dict[str, Any]) -> None:
        await self.db.execute(
            "UPDATE posts SET matched = 1, payload = ? WHERE channel = ? AND msg_id = ?",
            (json.dumps(payload, ensure_ascii=False), channel, msg_id),
        )
        await self.db.commit()

    async def mark_sent(self, channel: str, msg_id: int) -> None:
        await self.db.execute(
            "UPDATE posts SET sent = 1, sent_ts = ? WHERE channel = ? AND msg_id = ?",
            (int(time.time()), channel, msg_id),
        )
        await self.db.commit()

    async def pending(self, limit: int) -> list[dict[str, Any]]:
        """Отобранные, но ещё не отправленные посты — самые залайканные первыми."""
        cur = await self.db.execute(
            """
            SELECT channel, msg_id, payload FROM posts
            WHERE matched = 1 AND sent = 0 AND payload IS NOT NULL
            ORDER BY reactions DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = await cur.fetchall()
        return [
            {"channel": r["channel"], "msg_id": r["msg_id"], **json.loads(r["payload"])}
            for r in rows
        ]

    async def pending_count(self) -> int:
        cur = await self.db.execute("SELECT COUNT(*) AS c FROM posts WHERE matched = 1 AND sent = 0")
        row = await cur.fetchone()
        return int(row["c"]) if row else 0

    async def baseline(self, channel: str, sample: int) -> tuple[float, int]:
        """Медиана реакций по последним `sample` постам канала и размер выборки."""
        cur = await self.db.execute(
            "SELECT reactions FROM posts WHERE channel = ? ORDER BY msg_id DESC LIMIT ?",
            (channel, sample),
        )
        values = [int(r["reactions"]) for r in await cur.fetchall()]
        if not values:
            return 0.0, 0
        return float(median(values)), len(values)

    async def top(self, hours: int, limit: int) -> list[dict[str, Any]]:
        since = int(time.time()) - hours * 3600
        cur = await self.db.execute(
            """
            SELECT channel, msg_id, reactions, views, payload FROM posts
            WHERE ts >= ?
            ORDER BY reactions DESC
            LIMIT ?
            """,
            (since, limit),
        )
        result = []
        for row in await cur.fetchall():
            payload = json.loads(row["payload"]) if row["payload"] else {}
            result.append(
                {
                    "channel": row["channel"],
                    "msg_id": row["msg_id"],
                    "reactions": row["reactions"],
                    "views": row["views"],
                    **payload,
                }
            )
        return result

    async def stats_summary(self) -> dict[str, int]:
        cur = await self.db.execute(
            """
            SELECT
                COUNT(*)                                   AS total,
                COALESCE(SUM(matched), 0)                  AS matched,
                COALESCE(SUM(sent), 0)                     AS sent
            FROM posts
            """
        )
        row = await cur.fetchone()
        return {"total": row["total"], "matched": row["matched"], "sent": row["sent"]}

    async def cleanup(self, keep_days: int) -> int:
        """Чистит старую статистику, чтобы БД не росла бесконечно."""
        cutoff = int(time.time()) - keep_days * 86400
        cur = await self.db.execute("DELETE FROM posts WHERE ts < ? AND (sent = 1 OR matched = 0)", (cutoff,))
        await self.db.commit()
        return cur.rowcount or 0

    # ── Подписчики ───────────────────────────────────────────────────────────

    async def add_subscriber(self, chat_id: int, username: str | None) -> None:
        await self.db.execute(
            """
            INSERT INTO subscribers (chat_id, username, added_ts, paused)
            VALUES (?, ?, ?, 0)
            ON CONFLICT (chat_id) DO UPDATE SET paused = 0, username = excluded.username
            """,
            (chat_id, username, int(time.time())),
        )
        await self.db.commit()

    async def set_paused(self, chat_id: int, paused: bool) -> None:
        await self.db.execute(
            "UPDATE subscribers SET paused = ? WHERE chat_id = ?", (1 if paused else 0, chat_id)
        )
        await self.db.commit()

    async def remove_subscriber(self, chat_id: int) -> None:
        await self.db.execute("DELETE FROM subscribers WHERE chat_id = ?", (chat_id,))
        await self.db.commit()

    async def active_subscribers(self) -> list[int]:
        cur = await self.db.execute("SELECT chat_id FROM subscribers WHERE paused = 0")
        return [int(r["chat_id"]) for r in await cur.fetchall()]

    async def is_subscribed(self, chat_id: int) -> bool:
        cur = await self.db.execute(
            "SELECT 1 FROM subscribers WHERE chat_id = ? AND paused = 0", (chat_id,)
        )
        return await cur.fetchone() is not None

    # ── Служебные ключи ──────────────────────────────────────────────────────

    async def get_meta(self, key: str) -> str | None:
        cur = await self.db.execute("SELECT value FROM meta WHERE key = ?", (key,))
        row = await cur.fetchone()
        return row["value"] if row else None

    async def set_meta(self, key: str, value: str) -> None:
        await self.db.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?) "
            "ON CONFLICT (key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        await self.db.commit()
