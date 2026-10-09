"""The local blind labelling screen (protocol). Served on 127.0.0.1 only.

Reply text is data: the API returns JSON and the page writes it with `textContent`, under a
content security policy that allows no inline script, so a reply can never become markup.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from npcbench.review.labelling import (
    RATER_PATTERN,
    LabelError,
    LabelRecord,
    append_label,
    read_labels,
    serve_order,
)

STATIC = Path(__file__).parent / "static"
HOST = "127.0.0.1"
# Requests naming any other host are refused, so a DNS-rebinding page cannot use the screen.
ALLOWED_HOSTS = [HOST, "localhost"]
_SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self';"
        " base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
}


def create_labelling_app(
    items: dict[str, dict[str, Any]], *, labels_path: Path, seed: int
) -> FastAPI:
    """`items` maps reply id to its blinded view (`label_item`)."""
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    questions = {rid: [q["trait_id"] for q in item["questions"]] for rid, item in items.items()}

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.update(_SECURITY_HEADERS)
        return response

    app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/")
    def page() -> FileResponse:
        return FileResponse(STATIC / "label.html", media_type="text/html")

    @app.get("/api/next")
    def next_item(rater: str = Query(pattern=RATER_PATTERN)) -> dict[str, Any]:
        done = {r.reply_id for r in read_labels(labels_path) if r.rater == rater}
        remaining = [rid for rid in serve_order(items, seed=seed, rater=rater) if rid not in done]
        if not remaining:
            return {"done": True}
        return {"item": items[remaining[0]], "remaining": len(remaining)}

    @app.post("/api/labels", status_code=201)
    def post_label(record: LabelRecord) -> dict[str, str]:
        try:
            append_label(labels_path, record, questions)
        except LabelError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None
        return {"status": "saved"}

    return app


def serve(app: Any, *, port: int) -> None:
    """Run the screen on loopback only; it is never exposed beyond this machine."""
    uvicorn.run(app, host=HOST, port=port, log_level="warning")
