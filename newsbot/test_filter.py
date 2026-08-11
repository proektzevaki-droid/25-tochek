"""Проверка фильтра по порядку реакций на реальных примерах из каналов.

Запуск:  python test_filter.py
"""

from __future__ import annotations

import sys
from types import SimpleNamespace

from telethon.tl.types import ReactionEmoji, ReactionPaid

from collector import Candidate, _reaction_counts, evaluate
from config import FilterConfig, PatternFilter, RelativeFilter
from reactions import parse_pattern, pattern_label

failures: list[str] = []


def check(name: str, got: object, expected: object) -> None:
    if got == expected:
        print(f"  ok  {name}")
    else:
        failures.append(f"{name}: получено {got!r}, ожидалось {expected!r}")
        print(f"  FAIL {name}: получено {got!r}, ожидалось {expected!r}")


def fake_message(pairs: list[tuple[str | None, int]]) -> SimpleNamespace:
    """Сообщение с реакциями. None вместо эмодзи = платная звезда ⭐."""
    results = [
        SimpleNamespace(
            reaction=ReactionPaid() if emoji is None else ReactionEmoji(emoticon=emoji),
            count=count,
        )
        for emoji, count in pairs
    ]
    return SimpleNamespace(reactions=SimpleNamespace(results=results))


def candidate(pairs: list[tuple[str | None, int]], text: str = "новость") -> Candidate:
    total, breakdown, ranked = _reaction_counts(fake_message(pairs))
    return Candidate(
        channel_key="test",
        channel_title="Test",
        msg_id=1,
        ts=0,
        text=text,
        reactions=total,
        views=10_000,
        forwards=0,
        breakdown=breakdown,
        ranked=ranked,
        link="https://t.me/test/1",
        is_forward=False,
    )


def pattern_filter(*patterns: str, match: str = "prefix") -> FilterConfig:
    """Фильтр только по порядку реакций: пороги по количеству выключены."""
    return FilterConfig(
        mode="any",
        min_reactions=0,
        relative=RelativeFilter(enabled=False),
        pattern=PatternFilter(
            enabled=True,
            gate=True,
            match=match,
            patterns=[parse_pattern(p) for p in patterns],
        ),
    )


def post(*pairs: tuple[str, int]) -> Candidate:
    """Пост с платной звездой впереди — так их и отдаёт Telegram."""
    return candidate([(None, 1), *pairs])


print("\n1. Разбор шаблонов из config.yaml")
check("список эмодзи", pattern_label(parse_pattern(["💯", "❤️"])), "💯 ❤️")
check("слитная запись", pattern_label(parse_pattern("👍🔥")), "👍 🔥")
check("через запятую", pattern_label(parse_pattern("👍, 🔥")), "👍 🔥")
check("словами", pattern_label(parse_pattern("класс, огонь")), "класс огонь")
check("сердце без селектора", parse_pattern(["сердце"])[0].emojis, frozenset({"❤"}))
check("альтернативы в позиции", parse_pattern("👍|🔥")[0].emojis, frozenset({"👍", "🔥"}))
check("отрицание", parse_pattern("!🤬|😢")[0].negate, True)
check("звёздочка = любая", parse_pattern(["👍", "*"])[1].emojis, frozenset())

print("\n2. Платная звезда ⭐ не участвует в рейтинге")
total, breakdown, ranked = _reaction_counts(fake_message([(None, 5), ("👍", 113), ("🔥", 39)]))
check("рейтинг без звезды", ranked, ["👍", "🔥"])
check("в разбивке звезда осталась", ("⭐", 5) in breakdown, True)
check("сумма реакций считает всё", total, 157)

print("\n3. Реакции сортируются по убыванию, даже если API отдал вразнобой")
_, _, ranked = _reaction_counts(fake_message([("😢", 3), ("🔥", 39), ("👍", 113)]))
check("порядок по количеству", ranked, ["👍", "🔥", "😢"])

# ─────────────────────────────────────────────────────────────────────────────
# Осташко! Важное — 20 постов, которые Андрей отобрал как подходящие.
# Первое число в паре — количество реакций со скриншота.
# ─────────────────────────────────────────────────────────────────────────────
OSTASHKO_OK = [
    (("👍", 113), ("🔥", 39)),
    (("💯", 587), ("❤️", 66)),
    (("😁", 74), ("❤️", 23)),
    (("👍", 388), ("🤡", 32)),
    (("🔥", 520), ("👏", 87)),
    (("🔥", 401), ("❤️", 70)),
    (("👍", 263), ("👎", 40)),
    (("👍", 336), ("🔥", 137)),
    (("🤡", 344), ("🤣", 134)),
    (("👍", 323), ("🤡", 175)),
    (("💯", 613), ("❤️", 57)),
    (("👍", 476), ("💯", 170)),
    (("🔥", 466), ("👍", 99)),
    (("👍", 489), ("🔥", 225)),
    (("😁", 422), ("❤️", 70)),
    (("😁", 295), ("🤣", 150)),
    (("👍", 523), ("😁", 138)),
    (("❤️", 367), ("🙏", 262)),
    (("🤡", 983), ("🤣", 313)),
    (("🔥", 574), ("😁", 98)),
    (("👍", 1643), ("🤡", 201)),
    (("👍", 381), ("🙏", 170)),
    (("👍", 1114), ("🤡", 101)),
    (("🤡", 1118), ("🤣", 281)),
    (("👍", 304), ("🤔", 80)),
    (("🤣", 254), ("❤️", 91)),
]

# Посты из того же канала, которые Андрей отметил как ненужные.
OSTASHKO_NO = [
    (("🤬", 64), ("🤯", 10)),
    (("🤬", 223), ("🤡", 55)),
    (("🤬", 324), ("❤️", 22)),
    (("😢", 127), ("🤬", 62)),
    (("🤬", 649), ("❤️", 34)),
    (("🤬", 483), ("🙏", 79)),
    (("🤬", 574), ("🙏", 53)),
    (("🤬", 511), ("🙏", 85)),
    (("🤬", 554), ("🤡", 130)),
    # Здесь 🤬 только на втором месте, а впереди 🤡 — который в нужных постах
    # встречается. Одной первой позицией такой пост не отсечь.
    (("🤡", 723), ("🤬", 262)),
]

print("\n4. Осташко: гнев и скорбь не должны попадать в первые две реакции")
# Списки для позиций разные: во второй у Андрея проходят и 👎, и 🙏.
ostashko = pattern_filter("!🤬|😢|😭|🙏|💩|🤮|💔|🕊|👎, !🤬|😢|😭")
ok = sum(1 for pairs in OSTASHKO_OK if evaluate(post(*pairs), ostashko, 0, 0)[0])
check(f"проходят все {len(OSTASHKO_OK)} нужных поста", ok, len(OSTASHKO_OK))

blocked = sum(1 for pairs in OSTASHKO_NO if not evaluate(post(*pairs), ostashko, 0, 0)[0])
check(f"отсекаются все {len(OSTASHKO_NO)} ненужных", blocked, len(OSTASHKO_NO))

passed, reason = evaluate(post(("🤡", 723), ("🤬", 262)), ostashko, 0, 0)
check("🤡 впереди не спасает, если 🤬 идёт вторым", passed, False)
print(f"       причина: {reason}")
check(
    "а 🤡 с 🤣 вторым по-прежнему проходит",
    evaluate(post(("🤡", 1118), ("🤣", 281)), ostashko, 0, 0)[0],
    True,
)
check(
    "👎 вторым не мешает",
    evaluate(post(("👍", 263), ("👎", 40)), ostashko, 0, 0)[0],
    True,
)
check(
    "🙏 вторым не мешает",
    evaluate(post(("❤️", 367), ("🙏", 262)), ostashko, 0, 0)[0],
    True,
)

print("\n4b. Правила по одной первой позиции уже недостаточно")
first_only = pattern_filter("!🤬|😢|😭|🙏|💩|🤮|💔|🕊|👎")
check(
    "пост 🤡 → 🤬 проскакивает мимо однопозиционного правила",
    evaluate(post(("🤡", 723), ("🤬", 262)), first_only, 0, 0)[0],
    True,
)

print("\n5. Осташко: тот же набор перечислением пар")
# Запасной вариант, если правило окажется слишком широким.
pairs_filter = pattern_filter(
    "👍|🔥|💯|😁|🤡|❤️|🤣, 🔥|❤️|🤡|👏|👎|🤣|💯|👍|😁|🙏|🤔",
)
ok = sum(1 for pairs in OSTASHKO_OK if evaluate(post(*pairs), pairs_filter, 0, 0)[0])
check(f"проходят все {len(OSTASHKO_OK)} нужных поста", ok, len(OSTASHKO_OK))
blocked = sum(1 for pairs in OSTASHKO_NO if not evaluate(post(*pairs), pairs_filter, 0, 0)[0])
check(f"отсекаются все {len(OSTASHKO_NO)} ненужных", blocked, len(OSTASHKO_NO))
check(
    "но новая комбинация 🤩 + 🎉 уже не пройдёт",
    evaluate(post(("🤩", 500), ("🎉", 100)), pairs_filter, 0, 0)[0],
    False,
)
check(
    "а по правилу из п.4 — пройдёт",
    evaluate(post(("🤩", 500), ("🎉", 100)), ostashko, 0, 0)[0],
    True,
)

print("\n6. Украина Online — строго 🤬 первый, 😁 второй")
uaonline = pattern_filter("злой, смех")
check(
    "🤬 2.0K → 😁 149 → берём",
    evaluate(post(("🤬", 2000), ("😁", 149), ("🙏", 130), ("❤️", 102)), uaonline, 0, 0)[0],
    True,
)
passed, reason = evaluate(
    post(("🤬", 1600), ("🙏", 542), ("❤️", 198), ("🔥", 96)), uaonline, 0, 0
)
check("🤬 1.6K → 🙏 542 → пропускаем", passed, False)
print(f"       причина: {reason}")

print("\n7. Режимы сопоставления")
p = post(("🤬", 2000), ("😁", 149), ("🙏", 130))
check("anywhere: пара подряд в середине", evaluate(p, pattern_filter("😁, 🙏", match="anywhere"), 0, 0)[0], True)
check("top_set: порядок не важен", evaluate(p, pattern_filter("😁, 🤬", match="top_set"), 0, 0)[0], True)
check("prefix: порядок важен", evaluate(p, pattern_filter("😁, 🤬"), 0, 0)[0], False)
check(
    "top_set с отрицанием",
    evaluate(p, pattern_filter("!🤬, 🤬", match="top_set"), 0, 0)[0],
    True,
)

print("\n8. Шаблон короче рейтинга и длиннее его")
check(
    "шаблон из одной позиции не смотрит на вторую",
    evaluate(post(("👍", 500), ("💩", 400)), pattern_filter("👍"), 0, 0)[0],
    True,
)
check(
    "шаблон из трёх позиций не сработает на посте с двумя реакциями",
    evaluate(post(("👍", 500), ("🔥", 400)), pattern_filter("👍, 🔥, ❤️"), 0, 0)[0],
    False,
)
check("пост совсем без реакций", evaluate(post(), ostashko, 0, 0)[0], False)

print("\n9. Порог по количеству работает вместе с шаблоном")
strict = pattern_filter("👍🔥")
strict.min_reactions = 1000
strict.mode = "all"
check("шаблон совпал, реакций мало → мимо", evaluate(post(("👍", 113), ("🔥", 39)), strict, 0, 0)[0], False)
check("шаблон совпал, реакций много → берём", evaluate(post(("👍", 1500), ("🔥", 400)), strict, 0, 0)[0], True)

print()
if failures:
    print(f"❌ Провалено проверок: {len(failures)}")
    for line in failures:
        print(f"   • {line}")
    sys.exit(1)
print("✅ Все проверки пройдены")
