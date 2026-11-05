"""Free local compare/explain for chat: parse the question, then build names (answer.py builds the reply; no provider, no model)."""

import re

_PRONOUN = {"it", "i t", "its", "that", "this", "one"}
_WHAT = r"(?:wh?a?t(?:\s+(?:is|are)|'?s)|explain|describe|tell me about)"
_COMPARE = r"compar\w*"
_JOIN = r"(?:to|with|and|against|vs\.?|versus)"
_PATTERNS = [  # group a: an early subject that "it" refers to; b and c: the two names
    rf"^(?P<a>.*?)\s*(?:\b(?:and|an|also|then)\s+)?how\s+(?:does|do|is|are)\s+(?P<b>.+?)\s+{_COMPARE}\s+(?:to|with|against)\s+(?P<c>.+)$",
    r"difference\w*\s+(?:between|of)\s+(?P<b>.+?)\s+and\s+(?P<c>.+)$",
    rf"\b{_COMPARE}\s+(?P<b>.+?)\s+{_JOIN}\s+(?P<c>.+)$",
    r"^(?P<b>.+?)\s+(?:vs\.?|versus)\s+(?P<c>.+)$",
]
_ENDS = re.compile(r"\b(?:an|and|also|then|please|to|with)$")


def clean_name(text: str) -> str:
    text = re.sub(rf"^\s*(?:{_WHAT}\s+)?(?:(?:the|a|an)\s+)?", "", text.lower().replace("’", "'"))
    text = re.sub(r"[^\w\s'-]", " ", text)
    text = " ".join(text.split())
    while (stripped := _ENDS.sub("", text).strip()) != text:
        text = stripped
    return text


def parse_compare(question: str) -> tuple[str, str] | None:
    """The two cleaned names, or None. The first is "" when the question only says "it" (the caller supplies the selected Item)."""
    q = question.lower().replace("’", "'")
    for pattern in _PATTERNS:
        if match := re.search(pattern, q):
            groups = match.groupdict()
            first, second, third = clean_name(groups.get("a", "")), clean_name(groups["b"]), clean_name(groups["c"])
            # "wht is pony tail an how does I t compare to shovel": the early subject is the first Item and "it" refers to it
            first = first if first and second in _PRONOUN else second
            return ("" if first in _PRONOUN else first), third
    return None


def parse_what(question: str) -> str | None:
    match = re.match(rf"^\s*{_WHAT}\s+(.+)$", question.lower().replace("’", "'"))
    return clean_name(match[1]) if match else None


def parse_keep(question: str) -> str | None:
    """The cleaned name in "should I keep/remove X", "can I delete X", "get rid of X"; None when the question is not one."""
    match = re.match(
        r"^\s*(?:(?:should|can|could|do) i\s+(?:need to\s+)?)?(?:keep|remove|delete|drop|uninstall|get rid of)\s+(.+)$",
        question.lower().replace("’", "'"),
    )
    return clean_name(match[1]) if match else None
