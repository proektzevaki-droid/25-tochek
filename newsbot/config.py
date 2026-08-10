"""Загрузка и валидация конфигурации новостного бота."""

from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from reactions import parse_pattern

BASE_DIR = Path(__file__).resolve().parent

PATTERN_MODES = ("prefix", "anywhere", "top_set")


class ConfigError(Exception):
    """Конфигурация невалидна — запускаться нельзя."""


@dataclass
class RelativeFilter:
    enabled: bool = True
    factor: float = 2.0
    min_samples: int = 20
    floor: int = 20


@dataclass
class PatternFilter:
    """Фильтр по порядку реакций: какая эмодзи первая, какая вторая и т.д."""

    enabled: bool = False
    gate: bool = True  # True — обязательное условие; False — участвует в mode any/all
    match: str = "prefix"  # prefix | anywhere | top_set
    patterns: list[list[str]] = field(default_factory=list)


@dataclass
class FilterConfig:
    mode: str = "any"  # any | all
    min_reactions: int = 100
    relative: RelativeFilter = field(default_factory=RelativeFilter)
    pattern: PatternFilter = field(default_factory=PatternFilter)
    min_engagement_rate: float = 0.0
    min_views: int = 0
    keywords_include: list[str] = field(default_factory=list)
    keywords_exclude: list[str] = field(default_factory=list)
    skip_forwards: bool = False


@dataclass
class ScanConfig:
    interval_sec: int = 300
    min_age_minutes: int = 15
    max_age_hours: int = 24
    fetch_limit: int = 100
    pause_between_channels_sec: float = 2.0


@dataclass
class DeliveryConfig:
    mode: str = "instant"  # instant | digest
    digest_times: list[str] = field(default_factory=lambda: ["09:00", "19:00"])
    timezone: str = "Europe/Moscow"
    max_per_batch: int = 15
    send_interval_sec: float = 3.0
    text_preview_chars: int = 350


@dataclass
class ChannelConfig:
    username: str | None = None
    chat_id: int | None = None
    title: str | None = None
    filters: FilterConfig = field(default_factory=FilterConfig)

    @property
    def key(self) -> str:
        """Стабильный идентификатор канала для БД и логов."""
        return self.username.lower() if self.username else str(self.chat_id)

    @property
    def ref(self) -> str | int:
        """То, что скармливаем Telethon для резолва сущности."""
        return self.chat_id if self.chat_id is not None else f"@{self.username}"


@dataclass
class Config:
    api_id: int
    api_hash: str
    bot_token: str
    password: str | None
    db_path: Path
    session_path: Path
    owner_ids: list[int]
    scan: ScanConfig
    delivery: DeliveryConfig
    default_filters: FilterConfig
    channels: list[ChannelConfig]


def _as_filters(raw: dict[str, Any], base: FilterConfig) -> FilterConfig:
    """Накладывает переопределения из `raw` поверх базового фильтра."""
    rel_raw = raw.get("relative") or {}
    if not isinstance(rel_raw, dict):
        raise ConfigError("filter.relative должен быть объектом")

    relative = replace(
        base.relative,
        enabled=bool(rel_raw.get("enabled", base.relative.enabled)),
        factor=float(rel_raw.get("factor", base.relative.factor)),
        min_samples=int(rel_raw.get("min_samples", base.relative.min_samples)),
        floor=int(rel_raw.get("floor", base.relative.floor)),
    )

    mode = str(raw.get("mode", base.mode)).lower()
    if mode not in ("any", "all"):
        raise ConfigError(f"filter.mode должен быть 'any' или 'all', получено: {mode!r}")

    return FilterConfig(
        mode=mode,
        min_reactions=int(raw.get("min_reactions", base.min_reactions)),
        relative=relative,
        pattern=_as_pattern(raw.get("reaction_pattern"), base.pattern),
        min_engagement_rate=float(raw.get("min_engagement_rate", base.min_engagement_rate)),
        min_views=int(raw.get("min_views", base.min_views)),
        keywords_include=_as_words(raw.get("keywords_include", base.keywords_include)),
        keywords_exclude=_as_words(raw.get("keywords_exclude", base.keywords_exclude)),
        skip_forwards=bool(raw.get("skip_forwards", base.skip_forwards)),
    )


def _as_pattern(raw: Any, base: PatternFilter) -> PatternFilter:
    """Разбирает секцию reaction_pattern (или её сокращённую запись списком)."""
    if raw is None:
        return base
    if isinstance(raw, list):
        raw = {"enabled": True, "patterns": raw}
    if not isinstance(raw, dict):
        raise ConfigError("reaction_pattern должен быть списком шаблонов или объектом")

    match = str(raw.get("match", base.match)).lower()
    if match not in PATTERN_MODES:
        raise ConfigError(
            f"reaction_pattern.match должен быть одним из {PATTERN_MODES}, получено: {match!r}"
        )

    if "patterns" in raw:
        raw_patterns = raw.get("patterns") or []
        if not isinstance(raw_patterns, list):
            raise ConfigError("reaction_pattern.patterns должен быть списком")
        patterns = [p for p in (parse_pattern(item) for item in raw_patterns) if p]
        if raw_patterns and not patterns:
            raise ConfigError("Не удалось разобрать ни один шаблон в reaction_pattern.patterns")
    else:
        patterns = base.patterns

    enabled = bool(raw.get("enabled", base.enabled or bool(patterns)))
    if enabled and not patterns:
        raise ConfigError("reaction_pattern включён, но список patterns пуст")

    return PatternFilter(
        enabled=enabled,
        gate=bool(raw.get("gate", base.gate)),
        match=match,
        patterns=patterns,
    )


def _as_words(value: Any) -> list[str]:
    if not value:
        return []
    if not isinstance(value, list):
        raise ConfigError("Списки ключевых слов должны быть массивами строк")
    return [str(w).strip().lower() for w in value if str(w).strip()]


def _parse_channel(raw: Any, base: FilterConfig) -> ChannelConfig:
    if isinstance(raw, str):
        raw = {"username": raw}
    if not isinstance(raw, dict):
        raise ConfigError(f"Элемент channels должен быть строкой или объектом: {raw!r}")

    username = raw.get("username")
    chat_id = raw.get("id", raw.get("chat_id"))
    if not username and chat_id is None:
        raise ConfigError(f"У канала должен быть username или id: {raw!r}")

    if username:
        username = str(username).strip().lstrip("@")
        # Разрешаем писать полную ссылку — режем всё до последнего сегмента.
        if "t.me/" in username:
            username = username.rsplit("t.me/", 1)[1].strip("/")

    return ChannelConfig(
        username=username or None,
        chat_id=int(chat_id) if chat_id is not None else None,
        title=raw.get("title"),
        filters=_as_filters(raw, base),
    )


def load_config(path: str | Path | None = None) -> Config:
    """Читает .env + YAML и собирает готовый Config."""
    load_dotenv(BASE_DIR / ".env")

    cfg_path = Path(path) if path else BASE_DIR / "config.yaml"
    if not cfg_path.exists():
        raise ConfigError(
            f"Не найден файл конфигурации {cfg_path}. "
            "Скопируйте config.example.yaml в config.yaml и заполните."
        )

    raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ConfigError("Корень config.yaml должен быть объектом")

    api_id = os.getenv("TG_API_ID", "").strip()
    api_hash = os.getenv("TG_API_HASH", "").strip()
    bot_token = os.getenv("BOT_TOKEN", "").strip()
    missing = [
        name
        for name, value in (("TG_API_ID", api_id), ("TG_API_HASH", api_hash), ("BOT_TOKEN", bot_token))
        if not value
    ]
    if missing:
        raise ConfigError(
            "В .env не заданы: " + ", ".join(missing) + ". Смотрите .env.example."
        )
    if not api_id.isdigit():
        raise ConfigError("TG_API_ID должен быть числом")

    storage = raw.get("storage") or {}
    scan_raw = raw.get("scan") or {}
    delivery_raw = raw.get("delivery") or {}

    scan = ScanConfig(
        interval_sec=int(scan_raw.get("interval_sec", 300)),
        min_age_minutes=int(scan_raw.get("min_age_minutes", 15)),
        max_age_hours=int(scan_raw.get("max_age_hours", 24)),
        fetch_limit=int(scan_raw.get("fetch_limit", 100)),
        pause_between_channels_sec=float(scan_raw.get("pause_between_channels_sec", 2.0)),
    )
    if scan.min_age_minutes * 60 >= scan.max_age_hours * 3600:
        raise ConfigError("scan.min_age_minutes должен быть меньше scan.max_age_hours")

    delivery_mode = str(delivery_raw.get("mode", "instant")).lower()
    if delivery_mode not in ("instant", "digest"):
        raise ConfigError("delivery.mode должен быть 'instant' или 'digest'")

    digest_times = [str(t).strip() for t in (delivery_raw.get("digest_times") or ["09:00", "19:00"])]
    for t in digest_times:
        try:
            hh, mm = t.split(":")
            if not (0 <= int(hh) <= 23 and 0 <= int(mm) <= 59):
                raise ValueError
        except ValueError as exc:
            raise ConfigError(f"Некорректное время в delivery.digest_times: {t!r}") from exc

    delivery = DeliveryConfig(
        mode=delivery_mode,
        digest_times=digest_times,
        timezone=str(delivery_raw.get("timezone", "Europe/Moscow")),
        max_per_batch=int(delivery_raw.get("max_per_batch", 15)),
        send_interval_sec=float(delivery_raw.get("send_interval_sec", 3.0)),
        text_preview_chars=int(delivery_raw.get("text_preview_chars", 350)),
    )

    default_filters = _as_filters(raw.get("filter") or {}, FilterConfig())

    channels_raw = raw.get("channels") or []
    if not channels_raw:
        raise ConfigError("В config.yaml не указан ни один канал (секция channels)")
    channels = [_parse_channel(c, default_filters) for c in channels_raw]

    seen: set[str] = set()
    for ch in channels:
        if ch.key in seen:
            raise ConfigError(f"Канал {ch.key} указан в config.yaml дважды")
        seen.add(ch.key)

    def _resolve(p: str) -> Path:
        path_obj = Path(p)
        return path_obj if path_obj.is_absolute() else BASE_DIR / path_obj

    return Config(
        api_id=int(api_id),
        api_hash=api_hash,
        bot_token=bot_token,
        password=os.getenv("TG_PASSWORD") or None,
        db_path=_resolve(str(storage.get("db_path", "newsbot.db"))),
        session_path=_resolve(str(storage.get("session", "newsbot.session"))),
        owner_ids=[int(x) for x in (raw.get("owner_ids") or [])],
        scan=scan,
        delivery=delivery,
        default_filters=default_filters,
        channels=channels,
    )
