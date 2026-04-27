"""Password generator with entropy analysis and strength rating."""

import math
import secrets
import string


CHARSETS = {
    "digits":     string.digits,
    "lower":      string.ascii_lowercase,
    "upper":      string.ascii_uppercase,
    "alpha":      string.ascii_letters,
    "alnum":      string.ascii_letters + string.digits,
    "alnum+syms": string.ascii_letters + string.digits + "!@#$%^&*_-.",
    "full":       string.ascii_letters + string.digits + string.punctuation,
}

# (min_bits, max_bits, label, bar_char)
_STRENGTH_BANDS = [
    (0,  28,  "Very Weak",   "█"),
    (28, 40,  "Weak",        "██"),
    (40, 60,  "Fair",        "████"),
    (60, 80,  "Strong",      "██████"),
    (80, 999, "Very Strong", "████████"),
]


def entropy_bits(length: int, charset_size: int) -> float:
    if charset_size <= 1 or length <= 0:
        return 0.0
    return length * math.log2(charset_size)


def strength_label(bits: float) -> tuple[str, str]:
    """Return (label, bar_chars)."""
    for lo, hi, label, bar in _STRENGTH_BANDS:
        if lo <= bits < hi:
            return label, bar
    return "Very Strong", "████████"


def generate(
    length: int = 16,
    charset: str = "alnum+syms",
    count: int = 1,
    no_repeat: bool = False,
    pronounceable: bool = False,
) -> list[str]:
    """Generate *count* passwords."""
    chars = CHARSETS.get(charset, CHARSETS["alnum+syms"])
    results = []
    for _ in range(count):
        if pronounceable:
            results.append(_make_pronounceable(length))
        elif no_repeat:
            if length > len(chars):
                raise ValueError(
                    f"Cannot make {length}-char no-repeat password from a {len(chars)}-char set"
                )
            pool = list(chars)
            # Fisher-Yates via secrets for unbiased sampling
            chosen = []
            for i in range(length):
                j = i + secrets.randbelow(len(pool) - i)
                pool[i], pool[j] = pool[j], pool[i]
                chosen.append(pool[i])
            results.append("".join(chosen))
        else:
            results.append("".join(secrets.choice(chars) for _ in range(length)))
    return results


def _make_pronounceable(length: int) -> str:
    vowels     = "aeiou"
    consonants = "bcdfghjklmnpqrstvwxyz"
    pw = []
    for i in range(length):
        pw.append(secrets.choice(consonants if i % 2 == 0 else vowels))
    # Inject a digit and a symbol to boost strength
    if length >= 4:
        p1 = secrets.randbelow(length)
        p2 = (p1 + length // 2) % length
        pw[p1] = secrets.choice(string.digits)
        pw[p2] = secrets.choice("!@#$%&*")
    return "".join(pw)


def check_strength(password: str) -> dict:
    """Analyse a password's strength. Returns a detail dict."""
    has_lower = any(c in string.ascii_lowercase for c in password)
    has_upper = any(c in string.ascii_uppercase for c in password)
    has_digit = any(c in string.digits for c in password)
    has_sym   = any(c not in (string.ascii_letters + string.digits) for c in password)

    pool = 0
    if has_lower: pool += 26
    if has_upper: pool += 26
    if has_digit: pool += 10
    if has_sym:   pool += 32

    bits = entropy_bits(len(password), max(pool, 1))
    label, bar = strength_label(bits)

    return {
        "length":       len(password),
        "entropy_bits": round(bits, 1),
        "strength":     label,
        "bar":          bar,
        "charset_size": pool,
        "has_lower":    has_lower,
        "has_upper":    has_upper,
        "has_digit":    has_digit,
        "has_sym":      has_sym,
    }
