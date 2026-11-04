import json
import re
import threading
import webbrowser
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from .brief import append_line, brief, checklist_ids, frees
from .report import _known_costs
from .suggestions import Suggestion

HOST = "127.0.0.1"  # never bind wider: the scan holds the user's private setup
STATIC = Path(__file__).parent / "static"  # the frontend build (`npm --prefix frontend run build`); gitignored
BUILD_HINT = "the graph app is not built; run `npm --prefix frontend install && npm --prefix frontend run build`."
DEFAULT_CHECKLIST = Path.home() / ".cache" / "constellation" / "checklist.md"
_CHECKLIST_LOCK = threading.Lock()


class ChecklistEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[0-9a-f]{12}$")


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
    if path.is_relative_to((Path.home() / ".claude").resolve()):
        raise ValueError(f"Checklist {checklist} must be outside the Claude setup")
    if path == scan_file.resolve() or (path.exists() and scan_file.exists() and path.samefile(scan_file)):
        raise ValueError(f"Checklist {checklist} must not replace the scan file")
    return path


def create_app(scan_file: Path, checklist: Path | None = None) -> FastAPI:
    checklist = DEFAULT_CHECKLIST if checklist is None else checklist
    _checklist_path(checklist, scan_file)
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

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
            raise HTTPException(404, f"{scan_file} could not be read") from None
        return data, brief(data)

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

    app.mount("/", StaticFiles(directory=STATIC, html=True))  # last: the API route above wins
    return app


def serve(app: FastAPI, port: int, open_browser: bool) -> None:
    import uvicorn

    if open_browser:
        threading.Timer(1.0, webbrowser.open, [f"http://{HOST}:{port}/"]).start()
    uvicorn.run(app, host=HOST, port=port, log_level="warning")
