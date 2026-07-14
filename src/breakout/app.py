"""FastAPI application for the strictly-local BreakOut dashboard."""

from __future__ import annotations

import base64
import hashlib
import os
import secrets
import signal
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlencode

from fastapi import BackgroundTasks, FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from breakout.jobs import JobManager
from breakout.models import JSONRecord, SourceConnector
from breakout.spotify import SPOTIFY_SCOPES, SpotifyConnector, SpotifyError, SpotifyOAuth
from breakout.state import LocalState

HOST = "127.0.0.1"
PORT = 3000
REDIRECT_URI = f"http://{HOST}:{PORT}/auth/spotify/callback"
AUTHORIZE_URL = "https://accounts.spotify.com/authorize"
PACKAGE_ROOT = Path(__file__).parent


@dataclass(slots=True)
class BrowserSession:
    access_token: str | None = None
    profile: JSONRecord | None = None
    oauth_state: str | None = None
    code_verifier: str | None = None

    def disconnect(self) -> None:
        self.access_token = None
        self.profile = None
        self.oauth_state = None
        self.code_verifier = None


@dataclass
class MemorySessions:
    """OAuth values stay in process memory; cookies contain only an opaque ID."""

    values: dict[str, BrowserSession] = field(default_factory=dict)

    def get(self, session_id: str) -> BrowserSession:
        return self.values.setdefault(session_id, BrowserSession())

    def clear(self, session_id: str) -> None:
        self.values.pop(session_id, None)


def _pkce_verifier() -> str:
    return secrets.token_urlsafe(64)


def _pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def _safe_client_id(client_id: str) -> str | None:
    candidate = client_id.strip()
    if not (16 <= len(candidate) <= 128) or any(character.isspace() for character in candidate):
        return None
    return candidate


def _stop_local_process() -> None:
    """Ask the Uvicorn process to stop after the quit response is sent."""
    os.kill(os.getpid(), signal.SIGTERM)


def create_app(
    *,
    state: LocalState | None = None,
    oauth: SpotifyOAuth | None = None,
    connector_factory: Callable[[str], SourceConnector] | None = None,
    jobs: JobManager | None = None,
    sessions: MemorySessions | None = None,
    shutdown_callback: Callable[[], None] | None = None,
) -> FastAPI:
    app = FastAPI(title="BreakOut", docs_url=None, redoc_url=None)
    app.add_middleware(
        SessionMiddleware,
        secret_key=secrets.token_urlsafe(32),
        same_site="lax",
        https_only=False,  # the server is deliberately bound to loopback HTTP only
    )
    app.mount("/static", StaticFiles(directory=PACKAGE_ROOT / "static"), name="static")
    templates = Jinja2Templates(directory=PACKAGE_ROOT / "templates")
    local_state = state or LocalState()
    oauth_client = oauth or SpotifyOAuth()
    make_connector = connector_factory or (lambda token: SpotifyConnector(token))
    job_manager = jobs or JobManager()
    memory_sessions = sessions or MemorySessions()
    request_shutdown = shutdown_callback or _stop_local_process

    def browser_session(request: Request) -> tuple[str, BrowserSession]:
        session_id = request.session.get("breakout_session_id")
        if not isinstance(session_id, str):
            session_id = secrets.token_urlsafe(24)
            request.session["breakout_session_id"] = session_id
        return session_id, memory_sessions.get(session_id)

    def page(request: Request, **context: object):
        return templates.TemplateResponse(request=request, name="index.html", context=context)

    @app.get("/")
    async def index(request: Request):
        _, session = browser_session(request)
        return page(
            request,
            client_id_configured=local_state.spotify_client_id() is not None,
            profile=session.profile,
            message=request.query_params.get("message"),
            error=request.query_params.get("error"),
        )

    @app.post("/shutdown")
    async def shutdown_breakout(background_tasks: BackgroundTasks):
        background_tasks.add_task(request_shutdown)
        return RedirectResponse("/?message=BreakOut+is+closing.", status_code=303)

    @app.post("/setup/spotify")
    async def save_spotify_setup(request: Request, client_id: str = Form(...)):
        cleaned = _safe_client_id(client_id)
        if not cleaned:
            return page(
                request,
                client_id_configured=False,
                profile=None,
                error="Enter a valid Spotify Client ID without spaces.",
            )
        session_id, session = browser_session(request)
        local_state.set_spotify_client_id(cleaned)
        session.disconnect()
        memory_sessions.get(session_id)
        return RedirectResponse("/?message=Spotify+setup+saved.", status_code=303)

    @app.post("/setup/reset")
    async def reset_spotify_setup(request: Request):
        session_id, session = browser_session(request)
        local_state.clear_spotify_setup()
        session.disconnect()
        memory_sessions.clear(session_id)
        return RedirectResponse("/?message=Spotify+setup+was+reset.", status_code=303)

    @app.get("/auth/spotify/start")
    async def spotify_login(request: Request):
        client_id = local_state.spotify_client_id()
        if not client_id:
            return RedirectResponse("/?error=Set+up+a+Spotify+Client+ID+first.", status_code=303)
        _, session = browser_session(request)
        session.oauth_state = secrets.token_urlsafe(32)
        session.code_verifier = _pkce_verifier()
        query = urlencode(
            {
                "response_type": "code",
                "client_id": client_id,
                "redirect_uri": REDIRECT_URI,
                "scope": " ".join(SPOTIFY_SCOPES),
                "state": session.oauth_state,
                "code_challenge_method": "S256",
                "code_challenge": _pkce_challenge(session.code_verifier),
            }
        )
        return RedirectResponse(f"{AUTHORIZE_URL}?{query}", status_code=302)

    @app.get("/auth/spotify/callback")
    async def spotify_callback(
        request: Request, code: str | None = None, state_value: str | None = None
    ):
        _, session = browser_session(request)
        error = request.query_params.get("error")
        callback_state = state_value or request.query_params.get("state")
        if error:
            session.disconnect()
            return page(
                request,
                client_id_configured=local_state.spotify_client_id() is not None,
                profile=None,
                error=f"Spotify sign-in was not approved: {error}.",
            )
        if not code or not callback_state or not secrets.compare_digest(
            callback_state, session.oauth_state or ""
        ):
            session.disconnect()
            return page(
                request,
                client_id_configured=local_state.spotify_client_id() is not None,
                profile=None,
                error="Spotify sign-in could not be verified. Please try again.",
            )
        client_id = local_state.spotify_client_id()
        verifier = session.code_verifier
        if not client_id or not verifier:
            session.disconnect()
            return RedirectResponse("/?error=Spotify+setup+is+missing.", status_code=303)
        try:
            access_token = await oauth_client.exchange_code(client_id, code, verifier, REDIRECT_URI)
            connector = make_connector(access_token)
            profile = await connector.current_user()
            close = getattr(connector, "aclose", None)
            if close:
                await close()
        except SpotifyError as exc:
            session.disconnect()
            return page(
                request,
                client_id_configured=True,
                profile=None,
                error=str(exc),
            )
        session.access_token = access_token
        session.profile = profile
        session.oauth_state = None
        session.code_verifier = None
        return RedirectResponse("/?message=Spotify+is+connected.", status_code=303)

    @app.post("/auth/spotify/disconnect")
    async def disconnect_spotify(request: Request):
        _, session = browser_session(request)
        session.disconnect()
        return RedirectResponse("/?message=Spotify+was+disconnected.", status_code=303)

    @app.post("/exports")
    async def create_export(request: Request):
        session_id, session = browser_session(request)
        if not session.access_token:
            raise HTTPException(status_code=401, detail="Connect Spotify before exporting.")
        connector = make_connector(session.access_token)
        job = await job_manager.start(session_id, connector)
        return JSONResponse(job.public(), status_code=202)

    @app.get("/exports/{job_id}")
    async def export_status(request: Request, job_id: str):
        session_id, _ = browser_session(request)
        job = job_manager.get(job_id)
        if not job or job.owner_session_id != session_id:
            raise HTTPException(status_code=404, detail="Export not found.")
        return JSONResponse(job.public())

    @app.get("/exports/{job_id}/download")
    async def download_export(request: Request, job_id: str):
        session_id, _ = browser_session(request)
        job = job_manager.get(job_id)
        if (
            not job
            or job.owner_session_id != session_id
            or job.status != "succeeded"
            or not job.archive_path
            or not job.archive_path.is_file()
        ):
            raise HTTPException(status_code=404, detail="Export download not found.")
        return FileResponse(
            job.archive_path,
            media_type="application/zip",
            filename=job.archive_path.name,
        )

    return app
