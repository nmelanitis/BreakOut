import asyncio

import httpx

from breakout.spotify import SpotifyConnector


def run(coroutine):
    return asyncio.run(coroutine)


def test_export_normalizes_all_collections_and_keeps_playlist_order() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/v1/me":
            return httpx.Response(
                200, json={"id": "u1", "display_name": "Ada", "uri": "spotify:user:u1"}
            )
        if path == "/v1/me/playlists":
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": "p1",
                            "name": "Library",
                            "owner": {"id": "u1", "display_name": "Ada"},
                            "items": {"total": 2},
                            "external_urls": {"spotify": "https://open.spotify.com/playlist/p1"},
                        }
                    ],
                    "next": None,
                },
            )
        if path == "/v1/playlists/p1/items":
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "added_at": "2024-01-01T00:00:00Z",
                            "added_by": {"id": "u1"},
                            "item": {
                                "type": "track",
                                "id": "t1",
                                "uri": "spotify:track:t1",
                                "name": "Song",
                                "artists": [{"name": "Artist"}],
                                "album": {"name": "Album", "release_date": "2023-01-01"},
                                "external_ids": {"isrc": "ISRC1"},
                                "external_urls": {"spotify": "https://open.spotify.com/track/t1"},
                            },
                        }
                    ],
                    "next": None,
                },
            )
        if path == "/v1/me/tracks":
            return httpx.Response(200, json={"items": [], "next": None})
        if path == "/v1/me/albums":
            return httpx.Response(200, json={"items": [], "next": None})
        if path == "/v1/me/shows":
            return httpx.Response(200, json={"items": [], "next": None})
        if path == "/v1/me/episodes":
            return httpx.Response(200, json={"items": [], "next": None})
        if path == "/v1/me/audiobooks":
            return httpx.Response(200, json={"items": [], "next": None})
        if path == "/v1/me/following":
            return httpx.Response(
                200,
                json={
                    "artists": {
                        "items": [
                            {
                                "id": "a1",
                                "name": "Artist",
                                "genres": ["jazz"],
                                "uri": "spotify:artist:a1",
                            }
                        ],
                        "next": None,
                        "cursors": {"after": "a1"},
                    }
                },
            )
        raise AssertionError(f"Unexpected Spotify request: {path}")

    async def export():
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://unused")
        connector = SpotifyConnector("token", client=client)
        await connector.current_user()
        updates = []

        async def progress(phase, completed, total):
            updates.append((phase, completed, total))

        return await connector.export(progress)

    snapshot = run(export())
    assert snapshot.account["display_name"] == "Ada"
    assert snapshot.collections["playlist_items"][0]["position"] == 1
    assert snapshot.collections["playlist_items"][0]["isrc"] == "ISRC1"
    assert snapshot.collections["followed_artists"][0]["genres"] == ["jazz"]


def test_rate_limit_honors_retry_after() -> None:
    calls = 0
    delays: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, headers={"Retry-After": "0.25"})
        return httpx.Response(200, json={"id": "u1", "display_name": "Ada"})

    async def fake_sleep(delay: float) -> None:
        delays.append(delay)

    async def get_user():
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://unused")
        connector = SpotifyConnector("token", client=client, sleep=fake_sleep)
        return await connector.current_user()

    assert run(get_user())["id"] == "u1"
    assert calls == 2
    assert delays == [0.25]
