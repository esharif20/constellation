"""Redaction guard: nothing reaches the LLM without passing through redact()."""

import base64
import hashlib
import hmac
import math
import re
from collections import Counter
from collections.abc import Callable, Iterable
from itertools import pairwise
from typing import Any
from urllib.parse import quote, quote_plus

from .models import LLM, Embedder, TokenCounter

REDACTED = "[REDACTED]"

# Known key formats. Fail closed: a false positive only costs a slightly worse label.
_FORMATS = [
    re.compile(r"ghp_[A-Za-z0-9]{36}"),
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"xox[abprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"(?<=Bearer )[A-Za-z0-9._~+/=-]{16,}", re.IGNORECASE),
]

# Value under a secret-sounding name, whatever the value looks like. Names match as a substring (GH_TOKEN, --api-key, client_secret).
_NAME = r"[\w.-]*(?:token|key|secret|passw(?:or)?d|auth|credential|bearer)[\w.-]*"
_VALUE = r"""(?:"[^"\n]*"|'[^'\n]*'|[^\s"'&,;]+)"""
_FLAG = re.compile(rf"(?P<k>--?{_NAME}\s+)(?!--|[=:])(?P<v>{_VALUE})", re.IGNORECASE)  # --token VALUE (the = and : forms are _ASSIGNMENT)
_ASSIGNMENT = re.compile(
    rf"""(?P<k>{_NAME}["']?\s*[=:]\s*)(?P<v>{_VALUE})""", re.IGNORECASE
)  # KEY=VALUE, key: VALUE, "key": "VALUE", ?key=VALUE

# Backstop for secrets with no known format, name or value: long, digit-and-letter, random-looking runs.
_CANDIDATE = re.compile(r"[A-Za-z0-9+/_=-]{32,}")
_HEX = re.compile(r"[0-9a-fA-F]+")


def _entropy(s: str) -> float:
    """Shannon entropy in bits per character."""
    return -sum(n / len(s) * math.log2(n / len(s)) for n in Counter(s).values())


def _looks_random(s: str) -> bool:
    # shortcut: letters-only or digits-only runs are never judged random (paths look the same); other layers must catch them.
    if not (any(c.isdigit() for c in s) and any(c.isalpha() for c in s)):
        return False
    if sum(c.islower() or c in {"-", "_"} for c in s) / len(s) > 0.8:  # identifier-like: kebab, snake or camel case
        return False
    if sum(abs(ord(a) - ord(b)) == 1 for a, b in pairwise(s)) / len(s) > 0.3:  # abc..., 321...: varied but not random
        return False
    # Starting bars: hex 3.0 and base64-ish 4.0 bits/char (detect-secrets defaults to 3.0 and 4.5; lower here to fail closed).
    return _entropy(s) >= (3.0 if _HEX.fullmatch(s) else 4.0)


def _variants(value: str) -> set[str]:
    """A known value as it may appear after URL-encoding or base64."""
    return {
        value,
        quote_plus(value),
        quote(value, safe=""),  # pragma: no mutate  (any safe="<letters>" is equivalent: letters are never encoded)
        base64.b64encode(value.encode()).decode(),
    }


MIN_NEEDLE = 8


def _needle(value: str) -> bool:
    """Whether a known value may be matched literally: long enough, and not a piece of the marker (re-redacting one garbles it)."""
    # shortcut: values under 8 chars are never matched so "-" or "want" can't garble text; a short real secret would leak.
    return len(value) >= MIN_NEEDLE and value not in REDACTED


def redact(text: str, known: Iterable[str] = ()) -> str:
    # Encoding and base64 never shorten a value or turn it into a piece of the marker, so checking the value covers its variants.
    # Reverse order puts a needle before any needle that is its prefix, so the longest match wins at each position.
    needles = sorted({v for value in known if _needle(value) for v in _variants(value)}, reverse=True)
    if needles:  # one pass: a secret containing another goes whole, and a marker is never matched again
        text = re.sub("|".join(map(re.escape, needles)), REDACTED, text)
    for pattern in _FORMATS:
        text = pattern.sub(REDACTED, text)
    for pattern in (_FLAG, _ASSIGNMENT):
        text = pattern.sub(lambda m: m["k"] + REDACTED, text)
    return _CANDIDATE.sub(lambda m: REDACTED if _looks_random(m[0]) else m[0], text)


def unique_ids(ids: Iterable[str], known: Iterable[str], key: bytes) -> dict[str, str]:
    """Raw id -> saved id, for every id that redaction changes. Two secret-named Items would otherwise redact to the same id,
    so each gets a keyed 6-hex suffix: without the per-install key, a guessed secret cannot be checked against the suffix."""
    known = tuple(known)
    mapped = {i: redact(i, known) for i in ids}
    return {i: f"{r}~{hmac.new(key, i.encode(), hashlib.sha256).hexdigest()[:6]}" for i, r in mapped.items() if r != i}


def redact_tree(value: Any, known: Iterable[str] = (), ids: dict[str, str] | None = None) -> Any:
    """Redact every string (and dict key) in a JSON-like value: the one pass applied to whatever is written to disk.
    A string that is exactly an Item id in `ids` becomes its unique saved id; any other string goes through redact()."""
    known = tuple(known)
    ids = ids or {}
    if isinstance(value, str):
        return ids[value] if value in ids else redact(value, known)
    if isinstance(value, dict):
        return {redact_tree(k, known, ids): redact_tree(v, known, ids) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [redact_tree(v, known, ids) for v in value]
    return value


class ProviderError(Exception):
    """A model or embedder call failed. The message is already redacted, so it is safe to store and show."""


def _safely[T, R](call: Callable[[T], R], known: tuple[str, ...], argument: T) -> R:
    try:
        return call(argument)
    except Exception as error:
        # `from None`: the original error may echo a secret, and a traceback would print it.
        raise ProviderError(redact(f"{type(error).__name__}: {error}", known)) from None


def guarded(llm: LLM, known: Iterable[str] = ()) -> LLM:
    """The only way the app calls a model: every prompt is redacted first, and a provider failure becomes a ProviderError."""
    known = tuple(known)
    return lambda prompt: _safely(llm, known, redact(prompt, known))  # a bug in redact() must raise, not look like a provider failure


def guarded_embed(embed: Embedder, known: Iterable[str] = ()) -> Embedder:
    """Same rule for the embedder: a hosted one would receive Item text, so every text is redacted first."""
    known = tuple(known)
    return lambda texts: _safely(embed, known, [redact(text, known) for text in texts])


def guarded_count(count: TokenCounter, known: Iterable[str] = ()) -> TokenCounter:
    """Same rule for the token counter: the counting endpoint is a hosted provider, so every text is redacted first."""
    known = tuple(known)
    return lambda texts: _safely(count, known, [redact(text, known) for text in texts])
