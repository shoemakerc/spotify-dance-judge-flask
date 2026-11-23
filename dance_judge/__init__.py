"""The Dance Judge, Flask edition: pick a song and the server listens to its
30-second preview, then rules on whether you should dance to it."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path

from flask import Flask, abort, jsonify, render_template, request

from . import audio, itunes
from .analyze import Analysis, analyze
from .verdict import THRESHOLDS, Verdict, judge

# One from each verdict, banger to silly. iTunes track IDs.
SUGGESTIONS = [
    (269573364, "Billie Jean"),
    (617154366, "Get Lucky"),
    (1422648513, "Dancing Queen"),
    (1046187586, "Hallelujah"),
    (571977598, "Weightless"),
]

# Width and height of the "what the judge heard" drawing, in SVG units.
HEARD_W, HEARD_H = 600, 120


@dataclass(frozen=True)
class Hearing:
    """A song, what the judge heard in it, and the ruling."""

    song: itunes.Song
    analysis: Analysis
    verdict: Verdict


class NoSuchSong(Exception):
    pass


@lru_cache(maxsize=512)
def hear(track_id: int) -> Hearing:
    """Looks a song up, listens to its preview and judges it. A song always
    gets the same ruling, so rulings are kept; failures aren't, and get
    another try on the next visit."""
    song = itunes.lookup(track_id)
    if song is None:
        raise NoSuchSong(track_id)
    analysis = analyze(audio.decode(itunes.fetch_preview(song)), audio.SAMPLE_RATE)
    return Hearing(song, analysis, judge(analysis))


def outline(values: list[float], width: int = HEARD_W, height: int = HEARD_H) -> str:
    """A closed SVG path mirroring 0–1 values around the middle of a box."""
    mid, amp = height / 2, height * 0.38
    step = width / (len(values) - 1)
    top = [f"{i * step:.1f},{mid - v * amp:.1f}" for i, v in enumerate(values)]
    bottom = [f"{i * step:.1f},{mid + v * amp:.1f}" for i, v in enumerate(values)]
    return f"M{' L'.join(top)} L{' L'.join(reversed(bottom))} Z"


def clock(seconds: float) -> str:
    whole = round(seconds)
    return f"{whole // 60}:{whole % 60:02d}"


def create_app() -> Flask:
    app = Flask(__name__)
    # The main site's name, address, nav and footer links (see scripts/sync_site.py).
    site = json.loads((Path(__file__).parent / "site.json").read_text())
    app.jinja_env.filters["clock"] = clock
    # "B♭ minor" → ["B", "♭", " minor"], so a template can dress the accidental.
    app.jinja_env.filters["accidentals"] = lambda name: re.split("([♭♯])", name)
    app.jinja_env.globals.update(
        site=site,
        suggestions=SUGGESTIONS,
        thresholds=THRESHOLDS,
        heard_w=HEARD_W,
        heard_h=HEARD_H,
    )

    @app.context_processor
    def this_year():
        return {"year": date.today().year}

    @app.get("/")
    def index():
        query = request.args.get("q", "").strip()[:100]
        results, search_failed = None, False
        if len(query) >= 2:
            try:
                results = itunes.search(query)
            except itunes.Unavailable:
                search_failed = True
        return render_template("judge.html", query=query, results=results, search_failed=search_failed)

    @app.get("/song/<int:track_id>")
    def song(track_id: int):
        try:
            hearing = hear(track_id)
        except NoSuchSong:
            return _failed("Couldn’t find that song. Try searching for it instead.", 404)
        except itunes.Unavailable:
            return _failed("The record store isn’t answering. Give it a minute and try again.", 502)
        except audio.Unreadable:
            return _failed("The judge couldn’t hear this one. Try another song, or another version of it.", 502)
        page = render_template(
            "judge.html",
            hearing=hearing,
            shape=outline(hearing.analysis.envelope),
        )
        # The ruling never changes, so let browsers and proxies keep it a while.
        return page, {"Cache-Control": "public, max-age=3600"}

    @app.get("/api/song/<int:track_id>")
    def api_song(track_id: int):
        """The same ruling as JSON, for anyone who'd rather have the numbers."""
        try:
            hearing = hear(track_id)
        except NoSuchSong:
            abort(404, description="No such song.")
        except (itunes.Unavailable, audio.Unreadable) as error:
            abort(502, description=str(error))
        analysis = asdict(hearing.analysis)
        del analysis["envelope"]
        return jsonify(song=asdict(hearing.song), verdict=asdict(hearing.verdict), analysis=analysis)

    @app.get("/healthz")
    def healthz():
        return "ok"

    @app.errorhandler(404)
    def not_found(error):
        if request.path.startswith("/api/"):
            return jsonify(error=error.description), 404
        return _failed("There’s nothing at that address. Try searching for a song.", 404)

    @app.errorhandler(502)
    def bad_gateway(error):
        return jsonify(error=error.description), 502

    def _failed(message: str, status: int):
        return render_template("judge.html", failed=message), status

    return app
