"""Application factory."""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse

from liquid import __version__
from liquid.access import LoginRequired
from liquid.config import get_settings
from liquid.db import init_db, make_engine, session_factory
from liquid.render import flash, redirect, render
from liquid.routes.admin import router as admin_router
from liquid.routes.public import router as public_router
from liquid.security import SecurityMiddleware
from liquid.seed import seed

log = logging.getLogger("liquid")


def create_app() -> FastAPI:
    settings = get_settings()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    engine = make_engine(settings)
    factory = session_factory(engine)
    init_db(engine)
    with factory() as db:
        seed(db, settings)

    app = FastAPI(title="Liquid Software", version=__version__, docs_url=None, redoc_url=None)
    app.state.settings = settings
    app.state.session_factory = factory
    app.add_middleware(SecurityMiddleware, settings=settings)
    static_dir = Path(__file__).resolve().parent / "static"
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    app.include_router(public_router)
    app.include_router(admin_router)

    @app.exception_handler(LoginRequired)
    async def _login_required(request: Request, _exc: LoginRequired):
        flash(request, "error", "Sign in to continue.")
        return redirect("/admin/login")

    @app.exception_handler(HTTPException)
    async def _http_error(request: Request, exc: HTTPException):
        if request.url.path.startswith("/health"):
            return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
        accept = request.headers.get("accept", "")
        if "application/json" in accept and "text/html" not in accept:
            return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
        title = {403: "Not allowed", 404: "Not found", 429: "Slow down"}.get(exc.status_code, "Something went wrong")
        return render(request, "error.html", status=exc.status_code, title=title, message=str(exc.detail))

    log.info("Liquid Software %s ready (%s)", __version__, settings.env)
    return app
