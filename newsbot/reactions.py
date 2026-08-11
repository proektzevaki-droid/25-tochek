"""Нормализация эмодзи-реакций и разбор шаблонов вида «первый 👍, второй 🔥»."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import permutations

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


@dataclass(frozen=True)
class Slot:
    """Требование к одной позиции рейтинга реакций.

    emojis пустой  → подходит любая реакция («*»)
    negate = True  → подходит любая, КРОМЕ перечисленных («!🤬|😢»)
    """

    emojis: frozenset[str]
    negate: bool = False
    label: str = "*"

    def accepts(self, emoji: str) -> bool:
        if not self.emojis:
            return True
        return (emoji not in self.emojis) if self.negate else (emoji in self.emojis)


ANY_TOKENS = {"*", "любая", "любой", "любое", "any"}


def parse_slot(raw: object) -> Slot:
    """Разбирает одну позицию шаблона.

    "👍"          — ровно эта реакция
    "👍|🔥|💯"     — любая из перечисленных
    "!🤬|😢"       — любая, кроме перечисленных
    "*"           — любая
    """
    label = str(raw).strip()
    body = label
    negate = False
    if body[:1] in ("!", "^", "-"):
        negate = True
        body = body[1:].strip()

    if not body or body.lower() in ANY_TOKENS:
        return Slot(frozenset(), False, "*")

    emojis = frozenset(e for e in (resolve(alt) for alt in body.split("|")) if e)
    if not emojis:
        return Slot(frozenset(), False, "*")
    return Slot(emojis, negate, label)


def parse_pattern(raw: object) -> list[Slot]:
    """Шаблон — список требований по позициям, от первой реакции к последней.

    Записывать можно списком ["👍","🔥"], строкой "класс, огонь" или слитно "👍🔥".
    Длина шаблона задаёт, сколько первых позиций проверяется: шаблон из одного
    элемента смотрит только на первую реакцию и не трогает остальные.
    """
    if isinstance(raw, (list, tuple)):
        items = [str(x) for x in raw]
    else:
        text = str(raw).strip()
        if any(sep in text for sep in (",", ">")):
            items = _split_any(text, ",>")
        elif " " in text:
            items = text.split()
        elif any(ch in text for ch in "|!^*"):
            # Одна позиция со списком альтернатив: "👍|🔥|💯"
            items = [text]
        elif any(ch.isalpha() for ch in text):
            # Название реакции словом: «злой», «класс». Резать по буквам нельзя.
            items = [text]
        else:
            # Слитная запись «👍🔥» — режем по графемам верхнего уровня.
            items = _split_emoji_run(text)
    return [parse_slot(item) for item in items if str(item).strip()]


def pattern_label(pattern: list[Slot]) -> str:
    """Человекочитаемая запись шаблона для логов и команды /channels."""
    return " ".join(slot.label for slot in pattern)


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


def matches(ranked: list[str], pattern: list[Slot], mode: str = "prefix") -> bool:
    """Проверяет рейтинг реакций поста против шаблона.

    ranked  — эмодзи по убыванию числа реакций, платная звезда уже исключена.
    mode    — prefix: шаблон совпадает с началом рейтинга;
              anywhere: шаблон идёт подряд в любом месте рейтинга;
              top_set: те же требования к топу, но порядок не важен.
    """
    span = len(pattern)
    if not span or len(ranked) < span:
        return False

    if mode == "top_set":
        # Требований мало (обычно 2–3), поэтому перебор вариантов дешевле
        # аккуратного паросочетания и заметно понятнее.
        return any(
            all(slot.accepts(emoji) for slot, emoji in zip(pattern, perm))
            for perm in permutations(ranked[:span])
        )
    if mode == "anywhere":
        return any(
            all(slot.accepts(ranked[start + i]) for i, slot in enumerate(pattern))
            for start in range(len(ranked) - span + 1)
        )
    return all(slot.accepts(emoji) for slot, emoji in zip(pattern, ranked))
