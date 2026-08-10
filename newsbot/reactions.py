"""Нормализация эмодзи-реакций и разбор шаблонов вида «первый 👍, второй 🔥»."""

from __future__ import annotations

# Служебные символы, из-за которых одна и та же реакция выглядит по-разному:
# вариационные селекторы (❤️ против ❤) и модификаторы тона кожи.
_INVISIBLE = {"️", "︎"}
_SKIN_TONES = {chr(c) for c in range(0x1F3FB, 0x1F400)}

# Платная реакция звездой. В интерфейсе она всегда закреплена первой,
# поэтому в рейтинге «первый/второй смайл» не участвует.
PAID_MARKER = "⭐️⭐"  # заведомо не совпадёт с обычной ⭐
UNKNOWN_MARKER = "🧩"

# Понятные имена, чтобы в config.yaml можно было писать словами.
ALIASES: dict[str, str] = {
    "класс": "👍",
    "лайк": "👍",
    "палец": "👍",
    "палецвверх": "👍",
    "дизлайк": "👎",
    "палецвниз": "👎",
    "огонь": "🔥",
    "сердце": "❤",
    "любовь": "❤",
    "100": "💯",
    "100%": "💯",
    "стопроцентов": "💯",
    "клоун": "🤡",
    "слеза": "😢",
    "грусть": "😢",
    "плачу": "😭",
    # В Telegram два «смеющихся» смайла: 😁 в основном ряду и 🤣 отдельно.
    "смех": "😁",
    "улыбка": "😁",
    "ржач": "🤣",
    "ржака": "🤣",
    "угар": "🤣",
    "ха": "🤣",
    "вау": "😱",
    "шок": "😱",
    "молния": "⚡",
    "аплодисменты": "👏",
    "браво": "👏",
    "думаю": "🤔",
    "фу": "🤮",
    "какашка": "💩",
    "злой": "🤬",
    "злость": "🤬",
    "ярость": "🤬",
    "мат": "🤬",
    "молитва": "🙏",
    "спасибо": "🙏",
    "голубь": "🕊",
    "салют": "🎉",
    "сердцеразбито": "💔",
    "звезда": "⭐",
}


def normalize(emoji: str) -> str:
    """Приводит эмодзи к каноничному виду для сравнения."""
    return "".join(ch for ch in emoji if ch not in _INVISIBLE and ch not in _SKIN_TONES)


def resolve(token: str) -> str:
    """Превращает элемент шаблона (эмодзи или слово вроде «класс») в эмодзи."""
    token = str(token).strip()
    key = token.lower().replace(" ", "").replace("-", "").replace("_", "")
    if key in ALIASES:
        return normalize(ALIASES[key])
    return normalize(token)


def parse_pattern(raw: object) -> list[str]:
    """Шаблон можно писать списком ["👍","🔥"] или строкой "класс, огонь" / "👍🔥"."""
    if isinstance(raw, (list, tuple)):
        items = [str(x) for x in raw]
    else:
        text = str(raw).strip()
        if any(sep in text for sep in (",", "+", ">", "|")):
            items = [part for part in _split_any(text, ",+>|")]
        elif " " in text:
            items = text.split()
        else:
            # Слитная запись «👍🔥» — режем по графемам верхнего уровня.
            items = _split_emoji_run(text)
    return [e for e in (resolve(item) for item in items) if e]


def _split_any(text: str, separators: str) -> list[str]:
    parts = [text]
    for sep in separators:
        parts = [chunk for part in parts for chunk in part.split(sep)]
    return [p.strip() for p in parts if p.strip()]


def _split_emoji_run(text: str) -> list[str]:
    """Разбивает «👍🔥» на отдельные эмодзи, склеивая модификаторы с их базой."""
    out: list[str] = []
    for ch in text:
        if ch in _INVISIBLE or ch in _SKIN_TONES or ch == "‍":
            if out:
                out[-1] += ch
            continue
        if out and out[-1].endswith("‍"):
            out[-1] += ch
            continue
        out.append(ch)
    return [normalize(e) for e in out if normalize(e)]


def matches(ranked: list[str], pattern: list[str], mode: str = "prefix") -> bool:
    """Проверяет рейтинг реакций поста против шаблона.

    ranked  — эмодзи по убыванию числа реакций, платная звезда уже исключена.
    mode    — prefix: шаблон должен совпасть с началом рейтинга;
              anywhere: шаблон идёт подряд в любом месте рейтинга;
              top_set: те же эмодзи в топе, порядок не важен.
    """
    if not pattern or len(ranked) < len(pattern):
        return False

    if mode == "top_set":
        return set(pattern) == set(ranked[: len(pattern)])
    if mode == "anywhere":
        span = len(pattern)
        return any(ranked[i : i + span] == pattern for i in range(len(ranked) - span + 1))
    return ranked[: len(pattern)] == pattern
