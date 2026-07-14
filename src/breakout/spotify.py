"""Spotify OAuth and read-only library connector."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from breakout.models import ExportSnapshot, ExportWarning, JSONRecord, ProgressCallback

API_BASE_URL = "https://api.spotify.com/v1"
TOKEN_URL = "https://accounts.spotify.com/api/token"
SPOTIFY_SCOPES = (
    "playlist-read-private",
    "playlist-read-collaborative",
    "user-library-read",
    "user-follow-read",
    "user-read-playback-position",
)


class SpotifyError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class SpotifyAuthorizationError(SpotifyError):
    """The current user token can no longer be used."""


class SpotifyOAuth:
    """Authorization Code with PKCE token exchange; never retains refresh tokens."""

    async def exchange_code(
        self, client_id: str, code: str, code_verifier: str, redirect_uri: str
    ) -> str:
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.post(
                    TOKEN_URL,
                    data={
                        "client_id": client_id,
                        "grant_type": "authorization_code",
                        "code": code,
                        "redirect_uri": redirect_uri,
                        "code_verifier": code_verifier,
                    },
                    headers={"Accept": "application/json"},
                )
        except httpx.HTTPError as exc:
            raise SpotifyError("Could not reach Spotify to complete authorization.") from exc
        if response.is_error:
            raise SpotifyError("Spotify could not complete authorization.", response.status_code)
        access_token = response.json().get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise SpotifyError("Spotify did not return an access token.")
        return access_token


def _names(entities: Any) -> list[str]:
    if not isinstance(entities, list):
        return []
    return [
        str(entity["name"])
        for entity in entities
        if isinstance(entity, dict) and entity.get("name")
    ]


def _first_image(item: JSONRecord) -> str | None:
    images = item.get("images")
    if not isinstance(images, list):
        return None
    for image in images:
        if isinstance(image, dict) and isinstance(image.get("url"), str):
            return image["url"]
    return None


def _spotify_url(item: JSONRecord) -> str | None:
    urls = item.get("external_urls")
    if isinstance(urls, dict) and isinstance(urls.get("spotify"), str):
        return urls["spotify"]
    return None


def normalize_media(item: JSONRecord | None, fallback_type: str | None = None) -> JSONRecord:
    """Keep portable identifiers and descriptive fields, not raw provider responses."""

    if not item:
        return {
            "item_type": fallback_type or "unavailable",
            "item_id": None,
            "title": "Unavailable Spotify item",
            "unavailable": True,
        }

    album = item.get("album") if isinstance(item.get("album"), dict) else {}
    show = item.get("show") if isinstance(item.get("show"), dict) else {}
    external_ids = item.get("external_ids") if isinstance(item.get("external_ids"), dict) else {}
    creators = _names(item.get("artists")) or _names(item.get("authors"))
    if not creators and item.get("publisher"):
        creators = [str(item["publisher"])]

    return {
        "item_type": item.get("type", fallback_type),
        "item_id": item.get("id"),
        "uri": item.get("uri"),
        "url": _spotify_url(item),
        "title": item.get("name"),
        "creators": creators,
        "album_name": album.get("name"),
        "show_name": show.get("name"),
        "release_date": item.get("release_date") or album.get("release_date"),
        "duration_ms": item.get("duration_ms"),
        "isrc": external_ids.get("isrc"),
        "upc": external_ids.get("upc"),
        "total_tracks": item.get("total_tracks"),
        "total_episodes": item.get("total_episodes"),
        "total_chapters": item.get("total_chapters"),
        "description": item.get("description"),
        "image_url": _first_image(item) or _first_image(album) or _first_image(show),
        "is_local": item.get("is_local"),
        "is_playable": item.get("is_playable"),
    }


class SpotifyConnector:
    """Read-only Spotify connector that tolerates unavailable optional collections."""

    def __init__(
        self,
        access_token: str,
        client: httpx.AsyncClient | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._client = client or httpx.AsyncClient(timeout=30.0)
        self._owns_client = client is None
        self._sleep = sleep
        self._headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/json"}
        self._account: JSONRecord | None = None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def _request(self, path: str, params: dict[str, Any] | None = None) -> JSONRecord:
        for attempt in range(4):
            try:
                response = await self._client.get(
                    f"{API_BASE_URL}{path}", headers=self._headers, params=params
                )
            except httpx.HTTPError as exc:
                if attempt == 3:
                    raise SpotifyError("Could not reach Spotify. Please try again.") from exc
                await self._sleep(0.5 * (2**attempt))
                continue

            if response.status_code == 429 and attempt < 3:
                retry_after = response.headers.get("Retry-After", "1")
                try:
                    delay = min(max(float(retry_after), 0.0), 60.0)
                except ValueError:
                    delay = 0.5 * (2**attempt)
                await self._sleep(delay)
                continue
            if response.status_code == 401:
                raise SpotifyAuthorizationError(
                    "Spotify authorization expired. Connect Spotify again.", 401
                )
            if response.is_error:
                raise SpotifyError(
                    f"Spotify returned {response.status_code} for {path}.", response.status_code
                )
            data = response.json()
            if not isinstance(data, dict):
                raise SpotifyError(f"Spotify returned an unexpected response for {path}.")
            return data
        raise SpotifyError(f"Spotify rate limited {path}. Please try again later.", 429)

    async def current_user(self) -> JSONRecord:
        profile = await self._request("/me")
        self._account = {
            "id": profile.get("id"),
            "display_name": profile.get("display_name") or profile.get("id"),
            "uri": profile.get("uri"),
            "url": _spotify_url(profile),
        }
        return self._account

    async def _offset_pages(self, path: str) -> list[JSONRecord]:
        items: list[JSONRecord] = []
        offset = 0
        while True:
            page = await self._request(path, {"limit": 50, "offset": offset})
            page_items = page.get("items")
            if not isinstance(page_items, list):
                raise SpotifyError(f"Spotify returned malformed pagination for {path}.")
            items.extend(item for item in page_items if isinstance(item, dict))
            if not page.get("next"):
                return items
            if not page_items:
                raise SpotifyError(f"Spotify returned an empty page with a next link for {path}.")
            offset += len(page_items)

    async def _followed_artists(self) -> list[JSONRecord]:
        artists: list[JSONRecord] = []
        after: str | None = None
        while True:
            params: dict[str, Any] = {"type": "artist", "limit": 50}
            if after:
                params["after"] = after
            page = await self._request("/me/following", params)
            artist_page = page.get("artists")
            if not isinstance(artist_page, dict) or not isinstance(artist_page.get("items"), list):
                raise SpotifyError("Spotify returned malformed followed artists.")
            artists.extend(item for item in artist_page["items"] if isinstance(item, dict))
            cursors = artist_page.get("cursors")
            after = cursors.get("after") if isinstance(cursors, dict) else None
            if not artist_page.get("next") or not after:
                return artists

    @staticmethod
    def _warning(
        collection: str, error: SpotifyError, resource_id: str | None = None
    ) -> ExportWarning:
        return ExportWarning(
            code="collection_unavailable",
            message=str(error),
            collection=collection,
            resource_id=resource_id,
            status_code=error.status_code,
        )

    async def _optional(
        self,
        collection: str,
        fetcher: Callable[[], Awaitable[list[JSONRecord]]],
        warnings: list[ExportWarning],
    ) -> list[JSONRecord]:
        try:
            return await fetcher()
        except SpotifyAuthorizationError:
            raise
        except SpotifyError as error:
            if error.status_code in {403, 404}:
                warnings.append(self._warning(collection, error))
                return []
            raise

    async def export(self, progress: ProgressCallback) -> ExportSnapshot:
        account = self._account or await self.current_user()
        collections: dict[str, list[JSONRecord]] = {
            name: []
            for name in (
                "playlists",
                "playlist_items",
                "saved_tracks",
                "saved_albums",
                "followed_artists",
                "saved_shows",
                "saved_episodes",
                "saved_audiobooks",
            )
        }
        warnings: list[ExportWarning] = []

        await progress("Reading playlists", 0, None)
        playlists = await self._optional(
            "playlists", lambda: self._offset_pages("/me/playlists"), warnings
        )
        for index, playlist in enumerate(playlists, start=1):
            playlist_record = {
                "item_id": playlist.get("id"),
                "title": playlist.get("name"),
                "description": playlist.get("description"),
                "owner_id": playlist.get("owner", {}).get("id")
                if isinstance(playlist.get("owner"), dict)
                else None,
                "owner_name": playlist.get("owner", {}).get("display_name")
                if isinstance(playlist.get("owner"), dict)
                else None,
                "public": playlist.get("public"),
                "collaborative": playlist.get("collaborative"),
                "item_count": playlist.get("items", {}).get("total")
                if isinstance(playlist.get("items"), dict)
                else None,
                "uri": playlist.get("uri"),
                "url": _spotify_url(playlist),
                "image_url": _first_image(playlist),
            }
            collections["playlists"].append(playlist_record)
            playlist_id = playlist.get("id")
            if not isinstance(playlist_id, str):
                warnings.append(
                    ExportWarning(
                        "playlist_missing_id",
                        "Spotify returned a playlist without an ID.",
                        "playlists",
                    )
                )
                continue
            try:
                entries = await self._offset_pages(f"/playlists/{playlist_id}/items")
            except SpotifyAuthorizationError:
                raise
            except SpotifyError as error:
                warnings.append(self._warning("playlist_items", error, playlist_id))
                await progress("Reading playlists", index, len(playlists))
                continue
            for position, entry in enumerate(entries, start=1):
                item = entry.get("item") if isinstance(entry.get("item"), dict) else None
                media = normalize_media(item)
                collections["playlist_items"].append(
                    {
                        "playlist_id": playlist_id,
                        "playlist_name": playlist.get("name"),
                        "position": position,
                        "added_at": entry.get("added_at"),
                        "added_by_id": entry.get("added_by", {}).get("id")
                        if isinstance(entry.get("added_by"), dict)
                        else None,
                        **media,
                    }
                )
            await progress("Reading playlists", index, len(playlists))

        collection_specs: list[tuple[str, str, str]] = [
            ("saved_tracks", "/me/tracks", "track"),
            ("saved_albums", "/me/albums", "album"),
            ("saved_shows", "/me/shows", "show"),
            ("saved_episodes", "/me/episodes", "episode"),
            ("saved_audiobooks", "/me/audiobooks", "audiobook"),
        ]
        for collection, path, item_key in collection_specs:
            await progress(f"Reading {collection.replace('_', ' ')}", 0, None)
            saved_items = await self._optional(
                collection, lambda path=path: self._offset_pages(path), warnings
            )
            for entry in saved_items:
                item = entry.get(item_key) if isinstance(entry.get(item_key), dict) else None
                media = normalize_media(item, item_key)
                if collection == "saved_episodes" and isinstance(item, dict):
                    resume_point = item.get("resume_point")
                    media["resume_position_ms"] = (
                        resume_point.get("resume_position_ms")
                        if isinstance(resume_point, dict)
                        else None
                    )
                collections[collection].append({"added_at": entry.get("added_at"), **media})
            await progress(
                f"Reading {collection.replace('_', ' ')}", len(saved_items), len(saved_items)
            )

        await progress("Reading followed artists", 0, None)
        artists = await self._optional("followed_artists", self._followed_artists, warnings)
        for artist in artists:
            collections["followed_artists"].append(
                {
                    "item_id": artist.get("id"),
                    "title": artist.get("name"),
                    "genres": artist.get("genres") or [],
                    "uri": artist.get("uri"),
                    "url": _spotify_url(artist),
                    "image_url": _first_image(artist),
                }
            )
        await progress("Reading followed artists", len(artists), len(artists))
        return ExportSnapshot("spotify", account, collections, warnings)
