"""Local public Snapshot files; pattern scrubbing is not free-text anonymisation."""

import json
import os
from pathlib import Path
from typing import Any

from .assessment import compute
from .chat import LocalChat
from .snapshot import _public_text, expansions, snapshot

STATIC = Path(__file__).parent / "static"
NOTICE = (
    "This export does NOT anonymise free text. Review every retained name, description, label, reason and cluster name before publishing."
)
LIMITS = (
    "Known limits: bare usernames and machine names; unquoted paths with spaces; "
    "obfuscated emails; public hostnames outside URLs/emails; //server/share; $HOME/%USERPROFILE% forms."
)
_README = NOTICE + "\n\n" + LIMITS + "\n\nNothing was published. No backend or live servers are included.\n"

# The existing UI can read a static api/constellation file. All other API calls
# fail locally: search falls back to its local index and write/chat actions are unavailable.
_READ_ONLY = """(() => {
  const nativeFetch = globalThis.fetch.bind(globalThis);
  const api = new URL('api/', document.baseURI);
  const data = new URL('constellation', api);
  const shared = __DATA__;
  globalThis.__SNAPSHOT__ = { note: shared.note, questions: Object.keys(shared.canned) };
  const json = (body, status = 200) => Promise.resolve(new Response(JSON.stringify(body), {
    status, headers: { 'content-type': 'application/json' }
  }));
  globalThis.fetch = (input, init) => {
    const url = new URL(input instanceof Request ? input.url : input, document.baseURI);
    const method = (init?.method ?? (input instanceof Request ? input.method : 'GET')).toUpperCase();
    const refused = () => json({ detail: 'Read-only Snapshot' }, 404);
    const body = () => { try { return JSON.parse(init?.body); } catch { return {}; } };
    if (method === 'POST' && url.href === new URL('chat', api).href) {
      const q = String(body().question ?? '').trim();
      return Object.hasOwn(shared.canned, q) ? json(shared.canned[q]) : refused();
    }
    if (method === 'POST' && url.href === new URL('expand', api).href) {
      const id = body().id;
      return typeof id === 'string' && Object.hasOwn(shared.expansions, id)
        ? json({ item_id: id, status: 'expanded', items: shared.expansions[id], relations: [] }) : refused();
    }
    if (url.href.startsWith(api.href) && !(url.href === data.href && method === 'GET')) {
      return Promise.resolve(new Response('{"detail":"Read-only Snapshot"}', {
        status: 404, headers: { 'content-type': 'application/json' }
      }));
    }
    return nativeFetch(input, init);
  };
})();
"""
NOT_SHARED = "Usage and weekly history are not part of a shared snapshot."
QUESTIONS = (
    "What costs the most every session?",
    "What could I remove?",
    "What overlaps?",
    "What have I not used in 30 days?",
    "What changed this week?",
)
SNAPSHOT_NOTE = "This is a shared snapshot: only these questions are available."


def _scrub(value: Any) -> Any:
    if isinstance(value, str):
        return _public_text(value)
    if isinstance(value, list):
        return [_scrub(v) for v in value]
    if isinstance(value, dict):
        return {k: _scrub(v) for k, v in value.items()}
    return value


def canned(public: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Answers to the fixed questions, from the already-public data only (no usage, habits, history or weekly data exist there)."""
    chat, found = LocalChat(), compute(public)
    out: dict[str, dict[str, Any]] = {}
    for question in QUESTIONS:
        if question in QUESTIONS[3:]:  # usage questions: that data is never exported
            reply: dict[str, Any] = {"answer": NOT_SHARED, "blocks": None, "actions": [], "mode": "local", "cached": False}
        else:
            reply = chat.answer(public, question, [], lambda _: None, found)  # type: ignore[arg-type,return-value]  # pragma: no mutate  (selected and index are unused by these questions)
            if handoff := (reply["blocks"] or {}).get("handoff"):
                handoff["checklist_id"] = None  # no server to add to
        out[question] = _scrub(reply)
    return out


_ASSETS = {".js", ".css", ".woff", ".woff2", ".svg", ".png", ".ico"}


def _write(path: Path, content: bytes) -> None:
    for folder in reversed(path.parents):  # mkdir(parents=True) ignores mode for the parents
        if not folder.exists():
            folder.mkdir(mode=0o700)
    with path.open("xb") as stream:
        stream.write(content)
    path.chmod(0o600)


def write_snapshot(data: dict[str, Any], out: Path, expanded: object = None) -> None:
    """Write only scrubbed data and trusted build assets into a new, private directory."""
    target = out.resolve()
    config = os.environ.get("CLAUDE_CONFIG_DIR")  # a path, not a secret
    if ".claude" in (p.lower() for p in target.parts) or (config and target.is_relative_to(Path(config).resolve())):
        raise ValueError
    shown = snapshot(data)
    public = json.dumps(shown).encode()
    extras = json.dumps({"canned": canned(shown), "expansions": expansions(data, expanded), "note": SNAPSHOT_NOTE})
    entries = {p.name: p for p in STATIC.iterdir()}
    index, assets = entries["index.html"], entries["assets"]
    if index.is_symlink() or assets.is_symlink():
        raise ValueError
    html = index.read_text(encoding="utf-8")  # pragma: no mutate  (UTF-8 spelling)
    if "</head>" not in html:
        raise ValueError
    files = sorted(p for p in assets.rglob("*") if p.is_file() and p.suffix in _ASSETS)
    if not files:
        raise ValueError
    if any(p.is_symlink() for p in files):
        raise ValueError
    out.mkdir(mode=0o700)
    _write(out / "api/constellation", public)
    # "<" is escaped so no text can close a script early or start a tag.
    _write(out / "snapshot-readonly.js", _READ_ONLY.replace("__DATA__", extras.replace("<", "\\u003c")).encode())
    _write(out / "README.txt", _README.encode())
    _write(out / "index.html", html.replace("</head>", '<script src="./snapshot-readonly.js"></script></head>').encode())
    for source in files:
        target = out / source.relative_to(STATIC)
        _write(target, source.read_bytes())
