"""Human-looking identity material (name, handle-ish mail prefix, password).

The values have to look like a person wrote them: mixed-case names with a normal
distribution of first/last names, a mail prefix that looks like a nickname and a
password that follows the usual composition rules instead of a machine pattern.
"""

from __future__ import annotations

import random
import string
import unicodedata

FIRST_NAMES = [
    "Aiden", "Alice", "Amelia", "Anton", "Arjun", "Beatriz", "Caleb", "Camila",
    "Chloe", "Daniel", "Diego", "Elena", "Ethan", "Fatima", "Felix", "Fiona",
    "Gabriel", "Grace", "Hana", "Haruto", "Hassan", "Hugo", "Ines", "Ivan",
    "Jamal", "Jonas", "Julia", "Kenji", "Kira", "Lars", "Leila", "Lucas",
    "Marta", "Mateo", "Mei", "Mila", "Nadia", "Nikolai", "Noor", "Nora",
    "Oliver", "Priya", "Rafael", "Ravi", "Rosa", "Sanne", "Sara", "Simon",
    "Sofia", "Tariq", "Tessa", "Theo", "Valeria", "Viktor", "Yara", "Yuki",
    "Zoe", "Amir", "Bruno", "Clara", "Dilan", "Emil", "Freya", "Goran",
]

LAST_NAMES = [
    "Almeida", "Andersen", "Bakker", "Bauer", "Bellini", "Bergstrom", "Bianchi",
    "Cardoso", "Chen", "Dahl", "Delgado", "Duarte", "Eriksen", "Fischer",
    "Fontaine", "Garcia", "Gruber", "Hansen", "Iversen", "Jansen", "Jimenez",
    "Keller", "Khan", "Kobayashi", "Kovac", "Larsen", "Lindqvist", "Mancini",
    "Marchetti", "Mbeki", "Mendes", "Moretti", "Nakamura", "Novak", "Okafor",
    "Olsen", "Ortega", "Pereira", "Petrov", "Rossi", "Sato", "Schneider",
    "Silva", "Sorensen", "Tanaka", "Vasquez", "Virtanen", "Wagner", "Weber",
    "Yilmaz", "Zimmermann", "Kaur", "Reyes", "Nguyen", "Kim", "Park",
]

MAIL_PREFIX_WORDS = [
    "cedar", "maple", "willow", "harbor", "ember", "pebble", "cobalt", "fern",
    "lumen", "quartz", "sage", "tundra", "amber", "basil", "clover", "delta",
    "fjord", "glacier", "hazel", "iris", "jasper", "koi", "lark", "moss",
    "nectar", "onyx", "poppy", "raven", "saffron", "terra", "umber", "violet",
]


def _ascii(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()


def random_first_name(rng: random.Random | None = None) -> str:
    rng = rng or random
    return rng.choice(FIRST_NAMES)


def random_last_name(rng: random.Random | None = None) -> str:
    rng = rng or random
    return rng.choice(LAST_NAMES)


def random_display_name(rng: random.Random | None = None) -> str:
    """A display name a person would type for themselves."""
    rng = rng or random
    first = random_first_name(rng)
    last = random_last_name(rng)
    style = rng.random()
    if style < 0.55:
        return f"{first} {last}"
    if style < 0.8:
        return f"{first}.{last}".lower()
    return f"{first[0]}{last}"


def random_handle(rng: random.Random | None = None, taken: set[str] | None = None) -> str:
    """3-20 chars, starts with a letter or a digit, letters/digits/hyphen/underscore."""
    rng = rng or random
    taken = taken or set()
    for _ in range(200):
        word = rng.choice(MAIL_PREFIX_WORDS)
        style = rng.random()
        if style < 0.4:
            handle = word + str(rng.randint(2, 99))
        elif style < 0.7:
            handle = word + "_" + rng.choice(LAST_NAMES).lower().replace("-", "")[:6]
        elif style < 0.85:
            handle = word + str(rng.randint(100, 9999))
        else:
            handle = "".join(rng.choice(string.ascii_lowercase) for _ in range(3)) + word
        handle = handle[:20]
        if handle.lower() not in taken and not handle[0].isdigit():
            taken.add(handle.lower())
            return handle
    raise RuntimeError("could not build a handle")


def random_mail_prefix(rng: random.Random | None = None) -> str:
    """Prefix for the registration mailbox: reads like a person's nickname."""
    rng = rng or random
    word = rng.choice(MAIL_PREFIX_WORDS)
    suffix = rng.choice(
        [str(rng.randint(10, 9999)), str(rng.randint(100, 9999)), "_" + str(rng.randint(10, 99))]
    )
    return f"{word}{suffix}"


def random_password(rng: random.Random | None = None) -> str:
    """Password with the composition people actually use: word + digits + a symbol."""
    rng = rng or random
    words = [
        "Harbor", "Sunset", "Maple", "Cascade", "Meadow", "Copper", "Lantern",
        "Ridge", "Willow", "Sparrow", "Juniper", "Marble", "Cinder", "Drift",
    ]
    word = rng.choice(words)
    tail = str(rng.randint(100, 9999))
    symbol = rng.choice("!@#$%&*")
    middle = rng.choice(string.ascii_lowercase) * rng.randint(1, 2)
    password = f"{word}{middle}{tail}{symbol}"
    if rng.random() < 0.4:
        password = f"{word[0].lower()}{word[1:]}{middle}{tail}{symbol}"
    return password


def random_bio(rng: random.Random | None = None) -> str:
    rng = rng or random
    return rng.choice(
        [
            "Building small games in spare time.",
            "Pixel art, tiny scopes, long nights.",
            "I make games about odd little worlds.",
            "Design student, part-time puzzle maker.",
            "Prototype first, polish later.",
            "Here for the jam and the tiny arcade games.",
        ]
    )


def build_identity(mail_domain: str, rng: random.Random | None = None) -> dict:
    """One coherent identity: name, mailbox, password, handle, bio."""
    rng = rng or random
    first = random_first_name(rng)
    last = random_last_name(rng)
    return {
        "first_name": first,
        "last_name": last,
        "display_name": f"{first} {last}",
        "email": f"{random_mail_prefix(rng)}@{mail_domain}",
        "password": random_password(rng),
        "handle": random_handle(rng),
        "bio": random_bio(rng),
    }


__all__ = [
    "build_identity",
    "random_bio",
    "random_display_name",
    "random_handle",
    "random_mail_prefix",
    "random_password",
]

