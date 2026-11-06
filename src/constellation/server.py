import hashlib
import json
import os
import re
import stat
import threading
import unicodedata
import webbrowser
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator

from . import history as scan_history
from . import pins as pin_file
from . import retrieve
from . import weekly as weekly_summary
from .assessment import Assessed, compute
from .assessment import public as assessment_json
from .brief import append_line, build_brief, checklist_ids
from .chat import LocalChat
from .conflicts import conflicts
from .embeddings import fastembed_embedder
from .expansion import Query as ExpansionQuery
from .expansion import expand
from .explain import explain, render_explain
from .hook_safety import hook_safety
from .models import Embedder
from .receipt import receipt
from .removal import removal_preview
from .skill_search import find_skills
from .suggestions import Suggestion
from .triggers import trigger_audit

HOST = "127.0.0.1"  # never bind wider: the scan holds the user's private setup
STATIC = Path(__file__).parent / "static"  # the frontend build (`npm --prefix frontend run build`); gitignored
BUILD_HINT = "the graph app is not built; run `npm --prefix frontend install && npm --prefix frontend run build`."
DEFAULT_CHECKLIST = Path.home() / ".cache" / "constellation" / "checklist.md"
_CHECKLIST_LOCK = threading.Lock()


class ExpansionEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    id: str


class ChecklistEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[0-9a-f]{12}$")


class PinEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=400)


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=1, max_length=1000)
    selected_ids: list[str] = Field(default_factory=list, max_length=8)

    @field_validator("question")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("question must not be blank")
        return value


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    q: str = Field(max_length=retrieve.MAX_QUERY)
    limit: int = Field(default=retrieve.LIMIT, ge=1)


def local_only(request: Request) -> None:
    # Vite's dev proxy rewrites Host to its localhost target, so dev requests also pass.
    host = request.headers.get("host", "")
    match = re.fullmatch(r"(?:127\.0\.0\.1|localhost):([0-9]{1,5})", host)
    if match is None or not 1 <= int(match[1]) <= 65535:
        raise HTTPException(403, "A localhost Host and valid port are required")
    if request.method == "POST":
        origin = request.headers.get("origin")
        site = request.headers.get("sec-fetch-site")
        if (origin is not None and origin != f"http://{host}") or (site is not None and site not in ("same-origin", "none")):
            raise HTTPException(403, "A same-origin request is required")
        if request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
            raise HTTPException(415, "application/json is required")


_PREVIEW_MAX_BYTES = 1_000_000
_PREVIEW_KEYS = {"version", "pack", "items", "counts", "always_on", "overlaps", "already_installed", "compared", "note", "warnings"}


def _text(value: object, cap: int) -> str:
    if not isinstance(value, str) or len(value) > cap or any(unicodedata.category(c).startswith("C") for c in value):
        raise ValueError("bad text")
    return value


def _count(value: object) -> int | None:
    if value is None or (type(value) is int and 0 <= value <= 10_000_000):
        return value
    raise ValueError("bad number")


def _flag(value: object) -> bool:
    if type(value) is not bool:
        raise ValueError("bad flag")
    return value


def _exact(value: object, keys: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError("bad shape")
    return value


def _rows(value: object, cap: int) -> list[Any]:
    if not isinstance(value, list) or len(value) > cap:
        raise ValueError("bad list")
    return value


def _preview_file(path: Path) -> dict[str, Any]:
    """Rebuild a saved install preview field by field. The file is untrusted text: any odd shape, size or character raises ValueError."""
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)  # non-blocking, so a FIFO swapped in cannot hang a worker
    with os.fdopen(fd, "rb") as handle:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ValueError("not a regular file")
        raw = handle.read(_PREVIEW_MAX_BYTES + 1)
    if len(raw) > _PREVIEW_MAX_BYTES:
        raise ValueError("too large")
    data = _exact(json.loads(raw), _PREVIEW_KEYS)
    pack = _exact(data["pack"], {"name", "layout"})
    totals = _exact(data["always_on"], {"counted", "estimated", "unknown"})
    if data["version"] != 1 or pack["layout"] not in ("plugin", "pack", "skill"):
        raise ValueError("bad version")
    counts = data["counts"]
    if not isinstance(counts, dict) or len(counts) > 20:
        raise ValueError("bad counts")
    items = []
    for row in _rows(data["items"], 2000):
        row = _exact(row, {"id", "kind", "name", "description", "always_on", "estimated"})
        items.append(
            {
                "id": _text(row["id"], 400),
                "kind": _text(row["kind"], 40),
                "name": _text(row["name"], 80),
                "description": _text(row["description"], 200),
                "always_on": _count(row["always_on"]),
                "estimated": _flag(row["estimated"]),
            }
        )
    overlaps = []
    for row in _rows(data["overlaps"], 2000):
        row = _exact(row, {"new_id", "existing_id", "existing_name", "why"})
        overlaps.append(
            {
                "new_id": _text(row["new_id"], 400),
                "existing_id": _text(row["existing_id"], 400),
                "existing_name": _text(row["existing_name"], 80),
                "why": _text(row["why"], 40),
            }
        )
    for k in counts:  # counts, note and warnings are validated so a bad file is refused whole, but not served
        _text(k, 40), _count(counts[k])
    if data["note"] is not None:
        _text(data["note"], 400)
    for w in _rows(data["warnings"], 200):
        _text(w, 200)
    return {
        "version": 1,
        "pack": {"name": _text(pack["name"], 80), "layout": pack["layout"]},
        "items": [{k: i[k] for k in ("id", "kind", "name")} for i in items],  # only what the panel shows leaves the server
        "always_on": {k: _count(v) for k, v in totals.items()},
        "overlaps": overlaps,
        "already_installed": _flag(data["already_installed"]),
        "compared": _flag(data["compared"]),
    }


def _checklist_path(checklist: Path, scan_file: Path, what: str = "Checklist") -> Path:
    path = checklist.resolve()
    if ".claude" in path.parts or path.is_relative_to((Path.home() / ".claude").resolve()):
        raise ValueError(f"{what} {checklist} must be outside the Claude setup")
    if path == scan_file.resolve() or (path.exists() and scan_file.exists() and path.samefile(scan_file)):
        raise ValueError(f"{what} {checklist} must not replace the scan file")
    return path


# Counts and words only: no days, hashes or paths.
FIND_LIMIT = 8
FIND_UNAVAILABLE = (
    "Search by what a skill does needs your local ~/.claude, which this saved scan does not have. "
    'Run `constellation find "your words"` on the machine that has it.'
)
HABIT_FIELDS = ("sessions_used", "days_used", "idle_active_days", "mean_gap", "trend", "percentile", "pinned")


def create_app(
    scan_file: Path,
    checklist: Path | None = None,
    embedder: Embedder | None = None,
    *,
    config_dir: Path | None = None,
    expansion_query: ExpansionQuery | None = None,
    history: Path | None = None,
    preview: Path | None = None,
    habits: Path | None = None,
    pins: Path | None = None,
    weekly: Path | None = None,
) -> FastAPI:
    checklist = DEFAULT_CHECKLIST if checklist is None else checklist
    _checklist_path(checklist, scan_file)
    pins_file = pin_file.DEFAULT_CACHE if pins is None else pins
    _checklist_path(pins_file, scan_file, "Pins file")
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    body_limits = {"/api/chat": ("Chat", 16384), "/api/pin": ("Pin", 2048)}  # POST bodies are small; refuse the rest before reading them

    @app.middleware("http")
    async def limit_chat_body(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        if request.method == "POST" and request.url.path in body_limits:
            label, limit = body_limits[request.url.path]
            if "transfer-encoding" in request.headers:
                detail = f"Content-Length is required; chunked {label.lower()} requests are not supported"
                return JSONResponse({"detail": detail}, status_code=411)
            try:
                length = int(request.headers.get("content-length", "0"))
            except ValueError:
                return JSONResponse({"detail": "Invalid Content-Length"}, status_code=400)
            if length > limit:
                return JSONResponse({"detail": f"{label} request exceeds {limit} bytes"}, status_code=413)
        return await call_next(request)

    @app.get("/api/constellation", dependencies=[Depends(local_only)])
    def constellation() -> Response:
        try:
            text = scan_file.read_text()  # read per request so a fresh `scan` shows on reload
        except OSError:
            raise HTTPException(404, f"{scan_file} could not be read") from None
        return Response(text, media_type="application/json")

    def read_scan() -> dict[str, Any]:
        try:
            data = json.loads(scan_file.read_text())
            if not isinstance(data, dict) or not isinstance(data.get("items"), list):
                raise ValueError
        except (OSError, ValueError):
            raise HTTPException(404, "scan could not be read") from None
        return data

    def assessed(data: dict[str, Any]) -> Assessed:
        try:
            return compute(data, habits, pins_file)
        except (ValueError, TypeError, KeyError, AttributeError):
            raise HTTPException(404, "The saved scan could not be read") from None

    @app.get("/api/preview", dependencies=[Depends(local_only)])
    def get_preview() -> dict[str, Any]:  # the path is fixed at startup; nothing from the request names a file
        try:
            if preview is None:
                raise ValueError
            return _preview_file(preview)
        except (
            OSError,
            ValueError,
            RecursionError,
        ):  # deep nesting raises RecursionError; JSONDecodeError and UnicodeDecodeError are ValueErrors
            raise HTTPException(404, "no install preview") from None

    @app.get("/api/history", dependencies=[Depends(local_only)])
    def get_history() -> dict[str, Any]:
        data = read_scan()
        return scan_history.timeline(scan_history.DEFAULT_CACHE if history is None else history, data)

    @app.get("/api/lenses", dependencies=[Depends(local_only)])
    def get_lenses() -> dict[str, Any]:
        data = read_scan()
        return {"receipt": receipt(data), "hooks": hook_safety(data), "conflicts": conflicts(data), "triggers": trigger_audit(data)}

    @app.get("/api/removal", dependencies=[Depends(local_only)])
    def get_removal(id: str) -> dict[str, Any]:
        try:
            return removal_preview(read_scan(), id)
        except (KeyError, TypeError, AttributeError, ValueError):
            raise HTTPException(404, "no such Item in the saved scan") from None

    @app.get("/api/explain", dependencies=[Depends(local_only)])
    def get_explain(public: bool = False) -> dict[str, Any]:
        data = read_scan()
        summary = explain(data, public)
        return {**summary, "text": render_explain(summary)}

    def checklist_state(built: dict[str, Any]) -> dict[str, Any]:
        path = _checklist_path(checklist, scan_file)
        try:
            text = path.read_text()
        except FileNotFoundError:
            text = ""
        ids = checklist_ids(text)
        rows = [row for group in ("safe", "look") for row in built[group]["rows"] if row["id"] in ids]
        removed = {row["removes"]: row["saves"] for row in rows if row["removes"]}  # each Item once, however many rows name it
        known = [v for v in removed.values() if v is not None]
        return {
            "path": str(checklist),
            "ids": ids,
            "frees": sum(known) if known else None,
            "unknown_rows": len(ids) - sum(row["saves"] is not None for row in rows),
        }

    def built_brief(data: dict[str, Any], found: Assessed | None = None) -> dict[str, Any]:
        found = found or assessed(data)
        built = build_brief(data, found.assessments, found.evidence)
        built["evidence"]["ledger"] = found.ledger
        return built

    @app.get("/api/assess", dependencies=[Depends(local_only)])
    def get_assess() -> dict[str, Any]:
        found = assessed(read_scan())
        ev = found.evidence
        return {
            "items": {id_: assessment_json(a) for id_, a in found.assessments.items()},
            "habits": {id_: {f: getattr(e, f) for f in HABIT_FIELDS} for id_, e in ev.items.items()},
            "evidence": {"sessions": ev.sessions, "active_days": ev.active_days, "span_days": ev.span_days, "ledger": found.ledger},
        }

    @app.get("/api/brief", dependencies=[Depends(local_only)])
    def get_brief() -> dict[str, Any]:
        data = read_scan()
        found = assessed(data)
        built = built_brief(data, found)
        try:
            with _CHECKLIST_LOCK:
                state = checklist_state(built)
        except (OSError, ValueError) as error:
            raise HTTPException(500, f"Could not read checklist {checklist}: {error}") from None
        # names and counts only; None until a second scan exists so the Brief hides the section
        try:
            week = weekly_summary.build(data, found, built, weekly)
        except (KeyError, ValueError, TypeError, AttributeError):  # the Brief works without it
            week = {"state": "first"}
        return {**built, "checklist": state, "weekly": week if week["state"] == "ready" else None}

    @app.post("/api/checklist", dependencies=[Depends(local_only)])
    def add_to_checklist(entry: ChecklistEntry) -> dict[str, Any]:
        built = built_brief(read_scan())
        row = next((row for group in ("safe", "look") for row in built[group]["rows"] if row["id"] == entry.id), None)
        if row is None:
            raise HTTPException(404, "That row is not in the current brief")
        suggestion = Suggestion(row["id"], row["kind"], tuple(row["item_ids"]), row["reason"], row["saves"])
        try:
            with _CHECKLIST_LOCK:
                added = append_line(_checklist_path(checklist, scan_file), suggestion)
                state = checklist_state(built)
        except (OSError, ValueError) as error:
            raise HTTPException(500, f"Could not write checklist {checklist}: {error}") from None
        return {"added": added, **state}

    @app.post("/api/pin", dependencies=[Depends(local_only)])
    def pin_item(entry: PinEntry) -> dict[str, Any]:
        if entry.id not in {i.get("id") for i in read_scan()["items"] if isinstance(i, dict)}:
            raise HTTPException(404, "That Item is not in the current scan")
        try:
            with _CHECKLIST_LOCK:
                added = pin_file.add(_checklist_path(pins_file, scan_file, "Pins file"), entry.id)
        except (OSError, ValueError) as error:
            raise HTTPException(500, f"Could not write the pins file: {error}") from None
        return {"pinned": True, "added": added}

    @app.post("/api/expand", dependencies=[Depends(local_only)])
    async def expand_item(entry: ExpansionEntry) -> Any:
        try:
            data = json.loads(scan_file.read_text())
        except (OSError, ValueError):
            raise HTTPException(404, "The scan could not be read") from None
        try:
            return await expand(data, entry.id, config_dir, expansion_query)
        except KeyError:
            raise HTTPException(404, "Unknown Item") from None
        except ValueError:
            raise HTTPException(422, "Invalid scan/config input") from None

    def read_items() -> dict[str, Any]:
        try:
            data = json.loads(scan_file.read_text())
            if not isinstance(data, dict) or not isinstance(data.get("items"), list):
                raise ValueError
            if any(
                not isinstance(item, dict) or any(not isinstance(item.get(k), str) for k in ("id", "name", "kind", "description"))
                for item in data["items"]
            ):
                raise ValueError
            if len({item["id"] for item in data["items"]}) != len(data["items"]):
                raise ValueError
        except (OSError, ValueError, TypeError, KeyError):
            raise HTTPException(404, "The saved scan could not be read") from None
        return data

    chat = LocalChat()

    @app.post("/api/chat", dependencies=[Depends(local_only)])
    def ask_chat(entry: ChatRequest) -> dict[str, Any]:
        data = read_items()
        ids = {item["id"] for item in data["items"]}
        if any(id_ not in ids for id_ in entry.selected_ids):
            raise HTTPException(404, "That Item is not in the current scan")
        try:
            return chat.answer(data, entry.question, entry.selected_ids, index_for, assessed(data))
        except (ValueError, TypeError, KeyError, AttributeError):
            raise HTTPException(404, "The saved scan could not be read") from None

    embed = embedder or fastembed_embedder()  # loads the model on first use, once
    search_lock = threading.Lock()
    current: list[tuple[str, retrieve.Index]] = []  # the index for the scan content last searched

    def index_for(items: list[dict[str, Any]]) -> retrieve.Index:
        key = hashlib.sha256(json.dumps(items, sort_keys=True).encode()).hexdigest()
        with search_lock:
            if not current or current[0][0] != key:
                index = retrieve.Index(items)
                # vectors are built off the request path; until they are ready (or if the embedder is missing) search is word-only
                threading.Thread(target=index.add_vectors, args=(embed, retrieve.DEFAULT_CACHE), daemon=True).start()
                if current:
                    current[0][1].close()
                current[:] = [(key, index)]
            return current[0][1]

    def search(q: str, limit: int) -> dict[str, Any]:
        index = index_for(read_items()["items"])
        return {"results": index.query(q, min(limit, 20)), "note": index.note}

    @app.get("/api/search", dependencies=[Depends(local_only)])
    def get_search(q: str = Query(max_length=retrieve.MAX_QUERY), limit: int = Query(retrieve.LIMIT, ge=1)) -> dict[str, Any]:
        return search(q, limit)

    @app.post("/api/search", dependencies=[Depends(local_only)])
    def post_search(entry: SearchRequest) -> dict[str, Any]:
        return search(entry.q, entry.limit)

    @app.get("/api/find", dependencies=[Depends(local_only)])
    def get_find(q: str = Query(max_length=retrieve.MAX_QUERY)) -> dict[str, Any]:
        # local words over names, descriptions, headings and file names; no model, nothing sent; needs the live config dir
        if config_dir is None or not config_dir.is_dir():
            return {"available": False, "results": [], "warnings": [], "note": FIND_UNAVAILABLE}
        hits, warnings = find_skills(q, config_dir)
        return {"available": True, "results": hits[:FIND_LIMIT], "warnings": warnings, "note": None}

    app.mount("/", StaticFiles(directory=STATIC, html=True))  # last: the API route above wins
    return app


def serve(app: FastAPI, port: int, open_browser: bool) -> None:
    import uvicorn

    if open_browser:
        threading.Timer(1.0, webbrowser.open, [f"http://{HOST}:{port}/"]).start()
    uvicorn.run(
        app, host=HOST, port=port, log_level="warning", timeout_graceful_shutdown=2
    )  # Ctrl-C must not wait on open browser connections
