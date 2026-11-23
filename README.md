# Dance Judge, Flask edition

How cool (or not cool) would you look busting moves to a certain song? Pick one, and let the Dance Judge be the… judge.

This is the Flask take on the [Dance Judge](https://shoemakerc.github.io/dance-judge/). You search for a song, the server downloads Apple's 30-second preview and listens to it (tempo, beat strength, key, loudness, timbre), and a page comes back with a verdict, Spotify-style danceability and energy scores, and a drawing of what the judge heard.

The [browser version](https://shoemakerc.github.io/dance-judge/) does its listening in JavaScript on your device. This one does it on the server, in Python with NumPy. To have a whole song judged from a file of your own, use the browser version, which never uploads it.

## Run it

It was built and tested on Python 3.13.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/flask --app dance_judge run --debug --port 5010
```

Then open http://localhost:5010. (Port 5000, Flask's default, is taken by AirPlay Receiver on a Mac.)

## What's there

| Address | What it gives |
|---|---|
| `/` | The search box and a few songs to try |
| `/?q=purple+rain` | Search results |
| `/song/1229320478` | A song's verdict. The number is its iTunes track ID, so the address is a share link |
| `/api/song/1229320478` | The same ruling as JSON, with every measurement |
| `/healthz` | `ok`, for a host's health check |

Pages work without JavaScript. With it you also get a play button and playhead on the drawing, a copy-link button, and a sign that the judge is listening while the next page loads.

## How it's put together

- `dance_judge/__init__.py`: the Flask app and its routes.
- `dance_judge/itunes.py`: search and lookup through the [iTunes Search API](https://performance-partners.apple.com/search-api), and the preview download. Apple asks for about 20 requests a minute at most, and every visitor's request leaves from this one server, so answers are remembered for six hours and searching happens on submit, not per keystroke.
- `dance_judge/audio.py`: decodes the preview with [PyAV](https://pyav.org/), which carries its own FFmpeg.
- `dance_judge/analyze.py`: the listening.
- `dance_judge/verdict.py`: turns the measurements into scores and one of the 2017 verdicts.
- `dance_judge/templates/`, `dance_judge/static/`: the pages. `judge.js` is the only script.

A song always gets the same ruling, so rulings are kept in memory and a second visit costs nothing.

## Staying in step with the browser version

The scoring weights were fit against Spotify's archived scores for 295 songs, using the browser version's analyzer (`scripts/calibrate-dance-judge.mjs` in [shoemakerc.github.io](https://github.com/shoemakerc/shoemakerc.github.io)). They only mean anything if this analyzer measures what that one does, so `analyze.py` is a port of `src/lib/dance-judge/analyze.ts`, and the tests hold it to that:

- `tests/clip.py` builds a ten-second clip from whole-number arithmetic, so JavaScript can build the identical samples.
- `tests/expected.json` is the browser analyzer's reading of that clip.
- `tests/test_analyze.py` checks that the port gives the same tempo, key and beats, and every measurement to nine significant figures.

If the browser analyzer or its weights change, port the change, copy the weights into `verdict.py`, and regenerate the expected reading (Node 22.18 or later, with the site repo checked out alongside):

```bash
node tests/make_expected.mjs ../shoemakerc.github.io/src/lib/dance-judge/analyze.ts
```

One thing differs on purpose. Stereo is mixed to mono as (L + R) / √2, the way the calibration's decoder did it, where the browser version averages the channels. Scores for the same song can therefore differ a little between the two, mostly in energy.

## Tests

```bash
.venv/bin/python -m pytest
```

They fake Apple's side, so they need no network.

## The site's look

The header, footer and base styles come from the main site, which publishes them for its side projects. `scripts/sync_site.py` downloads them into `dance_judge/site.json` and `dance_judge/static/site-base.css`. Both are committed, so the app runs without the sync; run it to pick up a change to the site's nav or styles.

## Put it online

Any host that can run a Python web server will do. The start command is:

```bash
gunicorn wsgi:app --workers 1 --threads 8 --timeout 60
```

One worker, so all requests share the same memory of past rulings.

`render.yaml` describes a free [Render](https://render.com) web service: in Render, choose New → Blueprint and point it at this repository. It hasn't been deployed yet, so treat that file as a starting point. Render's free services sleep after fifteen idle minutes, and the first visit after that is slow.

## History

I wrote the first version in 2017 to learn Flask, as a port of my Node [spotify-dance-judge](https://github.com/shoemakerc/spotify-dance-judge), and never finished it. It logged you in to Spotify and asked its Web API how danceable a song was; Spotify has since closed that data to hobby apps. That code is kept on the [`archive-2017`](https://github.com/shoemakerc/spotify-dance-judge-flask/tree/archive-2017) branch and the `legacy-2017` tag. It was built on [Shreyas Jaganmohan](https://github.com/drshrey)'s Spotify OAuth walkthrough for Flask.
