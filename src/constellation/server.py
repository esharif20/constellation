import threading
import webbrowser
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

HOST = "127.0.0.1"  # never bind wider: the scan holds the user's private setup
STATIC = Path(__file__).parent / "static"  # the frontend build (`npm --prefix frontend run build`); gitignored
BUILD_HINT = "the graph app is not built; run `npm --prefix frontend install && npm --prefix frontend run build`."


def create_app(scan_file: Path) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/api/constellation")
    def constellation() -> Response:
        try:
            text = scan_file.read_text()  # read per request so a fresh `scan` shows on reload
        except OSError:
            raise HTTPException(404, f"{scan_file} could not be read") from None
        return Response(text, media_type="application/json")

    app.mount("/", StaticFiles(directory=STATIC, html=True))  # last: the API route above wins
    return app


def serve(app: FastAPI, port: int, open_browser: bool) -> None:
    import uvicorn

    if open_browser:
        threading.Timer(1.0, webbrowser.open, [f"http://{HOST}:{port}/"]).start()
    uvicorn.run(app, host=HOST, port=port, log_level="warning")
