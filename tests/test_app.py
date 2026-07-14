import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

from breakout.app import REDIRECT_URI, create_app
from breakout.jobs import JobManager
from breakout.models import ExportSnapshot
from breakout.state import LocalState


class FakeOAuth:
    def __init__(self) -> None:
        self.requests = []

    async def exchange_code(self, client_id, code, verifier, redirect_uri):
        self.requests.append((client_id, code, verifier, redirect_uri))
        return "in-memory-access-token"


class FakeConnector:
    async def current_user(self):
        return {"id": "user-1", "display_name": "Ada", "uri": "spotify:user:user-1"}

    async def export(self, progress):
        await progress("Reading playlists", 1, 1)
        return ExportSnapshot(
            "spotify",
            {"id": "user-1", "display_name": "Ada"},
            {"playlists": [{"item_id": "p1", "title": "Library"}]},
            exported_at="2026-07-14T11:00:00Z",
        )

    async def aclose(self):
        return None


def make_client(tmp_path: Path):
    state = LocalState(tmp_path / "state.sqlite3")
    oauth = FakeOAuth()
    app = create_app(
        state=state,
        oauth=oauth,
        connector_factory=lambda token: FakeConnector(),
        jobs=JobManager(tmp_path / "exports"),
    )
    return TestClient(app), state, oauth


def connect_spotify(client: TestClient, oauth: FakeOAuth) -> None:
    client.post("/setup/spotify", data={"client_id": "a" * 32})
    start = client.get("/auth/spotify/start", follow_redirects=False)
    query = parse_qs(urlparse(start.headers["location"]).query)
    callback = client.get(
        f"/auth/spotify/callback?code=approved&state={query['state'][0]}",
        follow_redirects=False,
    )
    assert callback.status_code == 303
    assert oauth.requests[0][3] == REDIRECT_URI


def test_setup_screen_displays_required_authentication_guidance(tmp_path: Path) -> None:
    client, _, _ = make_client(tmp_path)
    with client:
        response = client.get("/")
    assert (
        "This application runs locally on your computer and is not exposed through a public web "
        "server."
        in response.text
    )
    assert "http://127.0.0.1:3000/auth/spotify/callback" in response.text
    assert "Create your Spotify developer app" in response.text
    assert "Save Client ID and continue" in response.text
    assert "Do not replace" in response.text
    assert "Your Spotify password is entered only on Spotify’s website" in response.text
    assert "Quit BreakOut" in response.text
    assert "Closing this browser does not stop BreakOut" in response.text


def test_quit_requests_local_shutdown(tmp_path: Path) -> None:
    shutdown_requests = []
    app = create_app(
        state=LocalState(tmp_path / "state.sqlite3"),
        shutdown_callback=lambda: shutdown_requests.append(True),
    )

    with TestClient(app) as client:
        response = client.post("/shutdown", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/?message=BreakOut+is+closing."
    assert shutdown_requests == [True]


def test_browser_setup_oauth_and_export_download(tmp_path: Path) -> None:
    client, state, oauth = make_client(tmp_path)
    with client:
        connect_spotify(client, oauth)
        assert state.spotify_client_id() == "a" * 32
        dashboard = client.get("/")
        assert "Connected Spotify account" in dashboard.text
        started = client.post("/exports")
        assert started.status_code == 202
        job_id = started.json()["id"]
        for _ in range(30):
            status = client.get(f"/exports/{job_id}").json()
            if status["status"] in {"succeeded", "failed"}:
                break
            time.sleep(0.02)
        assert status["status"] == "succeeded"
        download = client.get(status["download_url"])
        assert download.status_code == 200
        assert download.headers["content-type"] == "application/zip"
        assert download.content[:2] == b"PK"


def test_callback_rejects_wrong_state(tmp_path: Path) -> None:
    client, _, oauth = make_client(tmp_path)
    with client:
        client.post("/setup/spotify", data={"client_id": "a" * 32})
        client.get("/auth/spotify/start", follow_redirects=False)
        response = client.get("/auth/spotify/callback?code=approved&state=wrong")
    assert "could not be verified" in response.text
    assert not oauth.requests
