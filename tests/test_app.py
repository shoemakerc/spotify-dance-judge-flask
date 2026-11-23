"""The pages, with Apple's side faked so the tests need no network."""

import io
import wave

import numpy as np
import pytest
from clip import SAMPLE_RATE, clip

import dance_judge
from dance_judge import create_app, itunes

SONG = itunes.Song(
    id=42,
    title="Rhapsody in <Blue>",
    artist="The Fixtures",
    album="Test Pressing",
    year="1984",
    duration_ms=215000,
    preview_url="https://audio-ssl.itunes.apple.com/preview.m4a",
    artwork="https://is1-ssl.mzstatic.com/image/thumb/x/100x100bb.jpg",
    apple_url="https://music.apple.com/us/album/x/1?i=42",
)


def preview() -> bytes:
    out = io.BytesIO()
    with wave.open(out, "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(SAMPLE_RATE)
        f.writeframes((clip() * 32767).astype("<i2").tobytes())
    return out.getvalue()


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(itunes, "search", lambda query: [SONG] if "rhapsody" in query.lower() else [])
    monkeypatch.setattr(itunes, "lookup", lambda track_id: SONG if track_id == SONG.id else None)
    monkeypatch.setattr(itunes, "fetch_preview", lambda song: preview())
    dance_judge.hear.cache_clear()
    return create_app().test_client()


def test_front_page_offers_a_search_and_suggestions(client):
    page = client.get("/").get_data(as_text=True)
    assert 'name="q"' in page
    assert "/song/269573364#verdict" in page
    assert "Chris Shoemaker" in page


def test_search_lists_songs(client):
    page = client.get("/?q=rhapsody").get_data(as_text=True)
    assert "/song/42#verdict" in page
    assert "Rhapsody in &lt;Blue&gt;" in page  # escaped, not trusted
    assert "The Fixtures · Test Pressing" in page
    assert "3:35" in page
    assert "100x100bb" not in page  # artwork resized


def test_search_with_no_matches_says_so(client):
    assert "Nothing by that name" in client.get("/?q=zzzz").get_data(as_text=True)


def test_search_when_apple_is_down(client, monkeypatch):
    def down(query):
        raise itunes.Unavailable("timeout")

    monkeypatch.setattr(itunes, "search", down)
    response = client.get("/?q=rhapsody")
    assert response.status_code == 200
    assert "record store isn’t answering" in response.get_data(as_text=True)


def test_song_page_gives_the_verdict(client):
    response = client.get("/song/42")
    page = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "max-age" in response.headers["Cache-Control"]
    assert "The verdict" in page
    assert "100<span class=\"judge-unit\"> BPM</span>" in page
    assert "A minor" in page
    assert 'class="heard-beat"' in page
    assert SONG.preview_url in page
    assert "600x600bb" in page


def test_flat_keys_get_the_music_font(client, monkeypatch):
    real = dance_judge.judge

    def in_b_flat(analysis):
        verdict = real(analysis)
        return type(verdict)(**{**verdict.__dict__, "key": "B♭ major"})

    monkeypatch.setattr(dance_judge, "judge", in_b_flat)
    assert 'B<span class="accidental">♭</span> major' in client.get("/song/42").get_data(as_text=True)


def test_the_song_is_only_listened_to_once(client, monkeypatch):
    calls = []
    monkeypatch.setattr(itunes, "fetch_preview", lambda song: calls.append(song.id) or preview())
    client.get("/song/42")
    client.get("/song/42")
    client.get("/api/song/42")
    assert calls == [42]


def test_unknown_song(client):
    response = client.get("/song/7")
    assert response.status_code == 404
    assert "Couldn’t find that song" in response.get_data(as_text=True)


def test_unreadable_preview(client, monkeypatch):
    monkeypatch.setattr(itunes, "fetch_preview", lambda song: b"not audio")
    response = client.get("/song/42")
    assert response.status_code == 502
    assert "couldn’t hear this one" in response.get_data(as_text=True)
    # A failure isn't remembered: the next visit tries again.
    monkeypatch.setattr(itunes, "fetch_preview", lambda song: preview())
    assert client.get("/song/42").status_code == 200


def test_api_returns_the_numbers(client):
    body = client.get("/api/song/42").get_json()
    assert body["song"]["title"] == SONG.title
    assert body["verdict"]["tempo"] == 100
    assert 0 <= body["verdict"]["danceability"] <= 1
    assert "pulse" in body["analysis"]["features"]
    assert "envelope" not in body["analysis"]


def test_api_unknown_song_is_json(client):
    response = client.get("/api/song/7")
    assert response.status_code == 404
    assert response.get_json() == {"error": "No such song."}


def test_other_addresses_are_not_found(client):
    assert client.get("/song/not-a-number").status_code == 404
    assert client.get("/healthz").get_data(as_text=True) == "ok"


def test_previews_are_only_fetched_from_apple():
    elsewhere = itunes.Song(**{**SONG.__dict__, "preview_url": "https://example.com/preview.m4a"})
    with pytest.raises(itunes.Unavailable):
        itunes.fetch_preview(elsewhere)
    insecure = itunes.Song(**{**SONG.__dict__, "preview_url": "http://audio-ssl.itunes.apple.com/x.m4a"})
    with pytest.raises(itunes.Unavailable):
        itunes.fetch_preview(insecure)
