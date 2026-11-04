"""Local public Snapshot files; pattern scrubbing is not free-text anonymisation."""

import json
from pathlib import Path
from typing import Any

from .snapshot import snapshot

STATIC = Path(__file__).parent / "static"
NOTICE = "This export does NOT anonymise free text. Review every retained name, description, label and reason before publishing."
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
  globalThis.fetch = (input, init) => {
    const url = new URL(input instanceof Request ? input.url : input, document.baseURI);
    const method = (init?.method ?? (input instanceof Request ? input.method : 'GET')).toUpperCase();
    if (url.href.startsWith(api.href) && !(url.href === data.href && method === 'GET')) {
      return Promise.resolve(new Response('{"detail":"Read-only Snapshot"}', {
        status: 404, headers: { 'content-type': 'application/json' }
      }));
    }
    return nativeFetch(input, init);
  };
})();
"""
_ASSETS = {".js", ".css", ".woff", ".woff2", ".svg", ".png", ".ico"}


def _write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(content)
    path.chmod(0o600)


def write_snapshot(data: dict[str, Any], out: Path) -> None:
    """Write only scrubbed data and trusted build assets into a new, private directory."""
    if ".claude" in out.resolve().parts:
        raise ValueError
    public = json.dumps(snapshot(data)).encode()
    entries = {p.name: p for p in STATIC.iterdir()}
    index, assets = entries["index.html"], entries["assets"]
    if index.is_symlink() or assets.is_symlink():
        raise ValueError
    html = index.read_text()
    if "</head>" not in html:
        raise ValueError
    files = sorted(p for p in assets.rglob("*") if p.is_file() and p.suffix in _ASSETS)
    if not files:
        raise ValueError
    if any(p.is_symlink() for p in files):
        raise ValueError
    out.mkdir(mode=0o700)
    _write(out / "api/constellation", public)
    _write(out / "snapshot-readonly.js", _READ_ONLY.encode())
    _write(out / "README.txt", _README.encode())
    _write(out / "index.html", html.replace("</head>", '<script src="./snapshot-readonly.js"></script></head>').encode())
    for source in files:
        target = out / source.relative_to(STATIC)
        _write(target, source.read_bytes())
