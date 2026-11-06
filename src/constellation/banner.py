"""The terminal logo: a Cassiopeia glyph (five stars, one bright anchor) beside a 3-row wordmark. Pure: `render` returns lines."""

import sys

from .cli_reports import Style

OLIVE, STEEL, TEAL, DIM = "38;5;143", "38;5;110", "38;5;109", "2"
URL = "github.com/esharif20/constellation"
WIDE, NARROW, COMPACT = 87, 54, 54  # wide: glyph + wordmark + tagline; narrow: wordmark (+ glyph when it fits); below COMPACT: one line
GLYPH_UTF8 = ("⋆   ✦   ⋆", " ╲ ╱ ╲ ╱ ", "  ⋆   ⋆  ")
GLYPH_ASCII = ("*   +   *", " \\ / \\ / ", "  *   *  ")
FONT = {
    "C": (" _ ", "|  ", "|_ "),
    "O": (" _ ", "| |", "|_|"),
    "N": ("   ", "|\\|", "| |"),
    "S": (" _ ", "|_ ", " _|"),
    "T": ("___", " | ", " | "),
    "E": (" _ ", "|_ ", "|_ "),
    "L": ("   ", "|  ", "|_ "),
    "A": (" _ ", "|_|", "| |"),
    "I": ("___", " | ", "___"),
}
ART = tuple(" ".join(FONT[ch][row] for ch in "CONSTELLATION") for row in range(3))


def is_utf8(encoding: str | None) -> bool:
    return encoding is not None and encoding.lower().replace("_", "-") in ("utf-8", "utf8")


_PLAIN = str.maketrans(
    {"➤": ">", "▶": ">", "▸": ">", "·": "-", "…": "...", "█": "#", "░": ".", "✓": "v", "↑": "^", "↓": "v", "→": ">", "│": "|", "—": "-"}
)


def ascii_safe(text: str, encoding: str | None) -> str:
    """On a terminal that is not UTF-8, swap our symbols for plain ones, and anything else it cannot show for `?`, instead of crashing."""
    if is_utf8(encoding):
        return text
    return text.replace("↑↓", "Up/Dn").translate(_PLAIN).encode(encoding or "ascii", "replace").decode(encoding or "ascii")


def _c(st: Style, code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if st.color else text


def _fit(text: str, width: int, ellipsis: str) -> str:
    return text if len(text) <= width else text[: width - 1] + ellipsis


def _glyph(st: Style, utf8: bool) -> list[str]:
    anchor = "✦" if utf8 else "+"
    out = []
    for row in GLYPH_UTF8 if utf8 else GLYPH_ASCII:
        out.append("".join(ch if ch == " " else _c(st, TEAL if ch == anchor else DIM if ch in "╲╱\\/" else STEEL, ch) for ch in row))
    return out


def render(st: Style, version: str, utf8: bool | None = None) -> list[str]:
    if utf8 is None:
        utf8 = is_utf8(getattr(sys.stdout, "encoding", None))
    dot, ell = (" · ", "…") if utf8 else (" - ", ".")
    tagline = "Map your Claude setup"
    if st.width < COMPACT:
        mark = "⋆✦⋆" if utf8 else "*+*"
        return [
            f"{_c(st, STEEL, mark[0])}{_c(st, TEAL, mark[1])}{_c(st, STEEL, mark[2])} {_c(st, OLIVE, 'Constellation')}",
            _c(st, DIM, _fit(f"{tagline}{dot}{version}", st.width, ell)),
        ]
    art = [_c(st, OLIVE, row) for row in ART]
    glyph = _glyph(st, utf8)
    if st.width >= WIDE:
        meta = ["", _c(st, OLIVE, tagline), _c(st, DIM, version)]
        rows = [f"{glyph[i]}   {art[i]}" + (f"  {meta[i]}" if meta[i] else "") for i in range(3)]
        return [*rows, " " * 12 + _c(st, STEEL, URL)]
    lead = 12 if st.width >= 12 + len(ART[0]) else 0
    rows = [f"{glyph[i]}   {art[i]}" if lead else art[i] for i in range(3)]
    pad = " " * lead
    return [*rows, pad + _c(st, OLIVE, _fit(f"{tagline}{dot}{version}", st.width - lead, ell)), pad + _c(st, STEEL, URL)]
