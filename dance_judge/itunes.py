"""Songs come from Apple's iTunes Search API: no key, and every result has a
30-second preview the judge can listen to.

Apple asks for no more than about 20 requests a minute, and here every
visitor's search leaves from the one server, so answers are remembered for a
while and a search only happens when the form is submitted.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from urllib.parse import urlparse

import requests

API = "https://itunes.apple.com"
TIMEOUT = 10
# Previews are about 1 MB; anything far past that isn't one.
MAX_PREVIEW_BYTES = 8_000_000

_session = requests.Session()
_session.headers["User-Agent"] = "dance-judge-flask (+https://github.com/shoemakerc/spotify-dance-judge-flask)"


class Unavailable(Exception):
    """Apple didn't answer, or answered with an error."""


@dataclass(frozen=True)
class Song:
    id: int
    title: str
    artist: str
    album: str
    year: str
    duration_ms: int
    preview_url: str
    artwork: str
    apple_url: str

    def artwork_at(self, px: int) -> str:
        """Apple's artwork URLs take any size in place of the 100×100 they come with."""
        return re.sub(r"/\d+x\d+bb\.", f"/{px}x{px}bb.", self.artwork)


class _Remembered:
    """A small cache: answers kept for `seconds`, oldest dropped past `limit`."""

    def __init__(self, seconds: float, limit: int = 512):
        self.seconds, self.limit, self.items = seconds, limit, {}

    def get(self, key):
        hit = self.items.get(key)
        return hit[1] if hit and time.monotonic() - hit[0] < self.seconds else None

    def put(self, key, value):
        if len(self.items) >= self.limit:
            self.items.pop(next(iter(self.items)))
        self.items[key] = (time.monotonic(), value)
        return value


_answers = _Remembered(seconds=6 * 60 * 60)


def _request(path: str, **params: str) -> list[Song]:
    key = (path, tuple(sorted(params.items())))
    if (songs := _answers.get(key)) is not None:
        return songs
    try:
        res = _session.get(f"{API}/{path}", params={"country": "US", **params}, timeout=TIMEOUT)
        res.raise_for_status()
        results = res.json()["results"]
    except (requests.RequestException, ValueError, KeyError) as error:
        raise Unavailable(str(error)) from error
    return _answers.put(
        key,
        [
            Song(
                id=r["trackId"],
                title=r["trackName"],
                artist=r["artistName"],
                album=r.get("collectionName", ""),
                year=r.get("releaseDate", "")[:4],
                duration_ms=r.get("trackTimeMillis", 0),
                preview_url=r["previewUrl"],
                artwork=r.get("artworkUrl100", ""),
                apple_url=r["trackViewUrl"],
            )
            for r in results
            if r.get("kind") == "song" and r.get("previewUrl")
        ],
    )


def search(query: str) -> list[Song]:
    return _request("search", term=query, entity="song", limit="8")


def lookup(track_id: int) -> Song | None:
    songs = _request("lookup", id=str(track_id), entity="song")
    return songs[0] if songs else None


def fetch_preview(song: Song) -> bytes:
    """Downloads the preview. The address comes from Apple's own answer, but
    this server is the one fetching it, so it's held to Apple's hosts."""
    url = urlparse(song.preview_url)
    if url.scheme != "https" or not (url.hostname or "").endswith(".apple.com"):
        raise Unavailable(f"unexpected preview host: {url.hostname}")
    try:
        with _session.get(song.preview_url, timeout=TIMEOUT, stream=True) as res:
            res.raise_for_status()
            data = res.raw.read(MAX_PREVIEW_BYTES + 1, decode_content=True)
    except requests.RequestException as error:
        raise Unavailable(str(error)) from error
    if len(data) > MAX_PREVIEW_BYTES:
        raise Unavailable("preview too large")
    return data
