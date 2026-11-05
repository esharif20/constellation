import hashlib
import json
import re
import threading
import webbrowser
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator

from . import retrieve
from .brief import append_line, brief, checklist_ids, frees
from .chat import LocalChat
from .embeddings import fastembed_embedder
from .expansion import Query as ExpansionQuery
from .expansion import expand
from .explain import explain, render_explain
from .models import Embedder
from .receipt import receipt
from .report import _known_costs
from .suggestions import Suggestion

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


def _checklist_path(checklist: Path, scan_file: Path) -> Path:
    path = checklist.resolve()
    if ".claude" in path.parts or path.is_relative_to((Path.home() / ".claude").resolve()):
        raise ValueError(f"Checklist {checklist} must be outside the Claude setup")
    if path == scan_file.resolve() or (path.exists() and scan_file.exists() and path.samefile(scan_file)):
        raise ValueError(f"Checklist {checklist} must not replace the scan file")
    return path


def create_app(
    scan_file: Path,
    checklist: Path | None = None,
    embedder: Embedder | None = None,
    *,
    config_dir: Path | None = None,
    expansion_query: ExpansionQuery | None = None,
) -> FastAPI:
    checklist = DEFAULT_CHECKLIST if checklist is None else checklist
    _checklist_path(checklist, scan_file)
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def limit_chat_body(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        if request.method == "POST" and request.url.path == "/api/chat":
            if "transfer-encoding" in request.headers:
                return JSONResponse({"detail": "Content-Length is required; chunked chat requests are not supported"}, status_code=411)
            try:
                length = int(request.headers.get("content-length", "0"))
            except ValueError:
                return JSONResponse({"detail": "Invalid Content-Length"}, status_code=400)
            if length > 16384:
                return JSONResponse({"detail": "Chat request exceeds 16384 bytes"}, status_code=413)
        return await call_next(request)

    @app.get("/api/constellation", dependencies=[Depends(local_only)])
    def constellation() -> Response:
        try:
            text = scan_file.read_text()  # read per request so a fresh `scan` shows on reload
        except OSError:
            raise HTTPException(404, f"{scan_file} could not be read") from None
        return Response(text, media_type="application/json")

    def read_brief() -> tuple[dict[str, Any], dict[str, Any]]:
        try:
            data = json.loads(scan_file.read_text())
            if not isinstance(data, dict) or not isinstance(data.get("items"), list):
                raise ValueError
        except (OSError, ValueError):
            raise HTTPException(404, "scan could not be read") from None
        return data, brief(data)

    @app.get("/api/lenses", dependencies=[Depends(local_only)])
    def get_lenses() -> dict[str, Any]:
        data, _ = read_brief()
        return {"receipt": receipt(data)}

    @app.get("/api/explain", dependencies=[Depends(local_only)])
    def get_explain(public: bool = False) -> dict[str, Any]:
        data, _ = read_brief()
        summary = explain(data, public)
        return {**summary, "text": render_explain(summary)}

    def checklist_state(data: dict[str, Any]) -> dict[str, Any]:
        path = _checklist_path(checklist, scan_file)
        try:
            text = path.read_text()
        except FileNotFoundError:
            text = ""
        ids = checklist_ids(text)
        all_rows = brief(data, top=max(len(data["items"]), len(data.get("overlaps") or [])))
        rows = [row for group in ("cost", "pairs") for row in all_rows[group]["rows"] if row["id"] in ids]
        return {
            "path": str(checklist),
            "ids": ids,
            "frees": frees(rows, _known_costs(data)),
            "unknown_rows": len(ids) - sum(row["tokens_saved"] is not None for row in rows),
        }

    @app.get("/api/brief", dependencies=[Depends(local_only)])
    def get_brief() -> dict[str, Any]:
        data, summary = read_brief()
        try:
            with _CHECKLIST_LOCK:
                state = checklist_state(data)
        except (OSError, ValueError) as error:
            raise HTTPException(500, f"Could not read checklist {checklist}: {error}") from None
        return {**summary, "checklist": state}

    @app.post("/api/checklist", dependencies=[Depends(local_only)])
    def add_to_checklist(entry: ChecklistEntry) -> dict[str, Any]:
        data, summary = read_brief()
        row = next((row for group in ("cost", "pairs") for row in summary[group]["rows"] if row["id"] == entry.id), None)
        if row is None:
            raise HTTPException(404, "That row is not in the current brief")
        suggestion = Suggestion(row["id"], row["kind"], tuple(row["item_ids"]), row["reason"], row["tokens_saved"])
        try:
            with _CHECKLIST_LOCK:
                added = append_line(_checklist_path(checklist, scan_file), suggestion)
                state = checklist_state(data)
        except (OSError, ValueError) as error:
            raise HTTPException(500, f"Could not write checklist {checklist}: {error}") from None
        return {"added": added, **state}

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
            return chat.answer(data, entry.question, entry.selected_ids, index_for)
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

    app.mount("/", StaticFiles(directory=STATIC, html=True))  # last: the API route above wins
    return app


def serve(app: FastAPI, port: int, open_browser: bool) -> None:
    import uvicorn

    if open_browser:
        threading.Timer(1.0, webbrowser.open, [f"http://{HOST}:{port}/"]).start()
    uvicorn.run(app, host=HOST, port=port, log_level="warning")
