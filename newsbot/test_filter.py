"""Проверка фильтра по порядку реакций на реальных примерах из каналов.

Запуск:  python test_filter.py
"""

from __future__ import annotations

import sys
from types import SimpleNamespace

from telethon.tl.types import ReactionEmoji, ReactionPaid

from collector import Candidate, _reaction_counts, evaluate
from config import FilterConfig, PatternFilter, RelativeFilter
from reactions import parse_pattern

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


def pattern_filter(*patterns: list[str]) -> FilterConfig:
    """Фильтр только по порядку реакций: пороги по количеству выключены."""
    return FilterConfig(
        mode="any",
        min_reactions=0,
        relative=RelativeFilter(enabled=False),
        pattern=PatternFilter(enabled=True, gate=True, match="prefix", patterns=list(patterns)),
    )


print("\n1. Разбор шаблонов из config.yaml")
check("список эмодзи", parse_pattern(["💯", "❤️"]), ["💯", "❤"])
check("слитная запись", parse_pattern("👍🔥"), ["👍", "🔥"])
check("через запятую", parse_pattern("👍, 🔥"), ["👍", "🔥"])
check("словами", parse_pattern("класс, огонь"), ["👍", "🔥"])
check("словами: злой и смех", parse_pattern("злой, смех"), ["🤬", "😁"])
check("сердце без селектора", parse_pattern(["сердце"]), ["❤"])

print("\n2. Платная звезда ⭐ не участвует в рейтинге")
total, breakdown, ranked = _reaction_counts(fake_message([(None, 5), ("👍", 113), ("🔥", 39)]))
check("рейтинг без звезды", ranked, ["👍", "🔥"])
check("в разбивке звезда осталась", ("⭐", 5) in breakdown, True)
check("сумма реакций считает всё", total, 157)

print("\n3. Реакции сортируются по убыванию, даже если API отдал вразнобой")
_, _, ranked = _reaction_counts(fake_message([("😢", 3), ("🔥", 39), ("👍", 113)]))
check("порядок по количеству", ranked, ["👍", "🔥", "😢"])

print("\n4. Осташко! Важное — шаблоны 👍🔥 и 💯❤️")
ostashko = pattern_filter(parse_pattern("👍🔥"), parse_pattern("💯❤️"))

# Скриншот 1: ⭐ 👍113 🔥39 ❤️11 😢3
post = candidate([(None, 1), ("👍", 113), ("🔥", 39), ("❤️", 11), ("😢", 3)])
passed, reason = evaluate(post, ostashko, baseline=0, samples=0)
check("👍 первый, 🔥 второй → берём", passed, True)
print(f"       причина: {reason}")

# Скриншот 2: ⭐ 💯587 ❤️66 👍45 🤡18
post = candidate([(None, 1), ("💯", 587), ("❤️", 66), ("👍", 45), ("🤡", 18)])
passed, reason = evaluate(post, ostashko, baseline=0, samples=0)
check("💯 первый, ❤️ второй → берём", passed, True)
print(f"       причина: {reason}")

# Те же эмодзи, но в другом порядке — не подходит
post = candidate([(None, 1), ("🔥", 200), ("👍", 113), ("❤️", 11)])
passed, reason = evaluate(post, ostashko, baseline=0, samples=0)
check("🔥 первый, 👍 второй → пропускаем", passed, False)
print(f"       причина: {reason}")

print("\n5. Украина Online — шаблон 🤬😁")
uaonline = pattern_filter(parse_pattern("злой, смех"))

# Скриншот 1: ⭐ 🤬2.0K 😁149 🙏130 ❤️102
post = candidate([(None, 1), ("🤬", 2000), ("😁", 149), ("🙏", 130), ("❤️", 102)])
passed, reason = evaluate(post, uaonline, baseline=0, samples=0)
check("🤬 первый, 😁 второй → берём", passed, True)
print(f"       причина: {reason}")

# Скриншот 2: ⭐ 🤬1.6K 🙏542 ❤️198 🔥96 — второй смайл не тот
post = candidate([(None, 1), ("🤬", 1600), ("🙏", 542), ("❤️", 198), ("🔥", 96)])
passed, reason = evaluate(post, uaonline, baseline=0, samples=0)
check("🤬 первый, 🙏 второй → пропускаем", passed, False)
print(f"       причина: {reason}")

print("\n6. Режимы сопоставления")
post = candidate([(None, 1), ("🤬", 2000), ("😁", 149), ("🙏", 130)])
anywhere = pattern_filter(["😁", "🙏"])
anywhere.pattern.match = "anywhere"
check("anywhere: пара подряд в середине", evaluate(post, anywhere, 0, 0)[0], True)

top_set = pattern_filter(["😁", "🤬"])
top_set.pattern.match = "top_set"
check("top_set: те же двое в топе, порядок не важен", evaluate(post, top_set, 0, 0)[0], True)

prefix = pattern_filter(["😁", "🤬"])
check("prefix: порядок важен", evaluate(post, prefix, 0, 0)[0], False)

print("\n7. Порог по количеству продолжает работать вместе с шаблоном")
strict = pattern_filter(parse_pattern("👍🔥"))
strict.min_reactions = 1000
strict.mode = "all"
post = candidate([(None, 1), ("👍", 113), ("🔥", 39)])
check("шаблон совпал, но реакций мало → пропускаем", evaluate(post, strict, 0, 0)[0], False)
post = candidate([(None, 1), ("👍", 1500), ("🔥", 400)])
check("шаблон совпал и реакций много → берём", evaluate(post, strict, 0, 0)[0], True)

print("\n8. Пост совсем без реакций")
post = candidate([])
check("нет реакций → пропускаем", evaluate(post, ostashko, 0, 0)[0], False)

print()
if failures:
    print(f"❌ Провалено проверок: {len(failures)}")
    for line in failures:
        print(f"   • {line}")
    sys.exit(1)
print("✅ Все проверки пройдены")
