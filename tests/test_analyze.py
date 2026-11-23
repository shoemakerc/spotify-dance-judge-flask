"""The NumPy analyzer has to measure what the browser version's does, since
the scoring weights were fit to that one. expected.json is the browser
analyzer's reading of the clip in clip.py (see make_expected.mjs)."""

import json
import warnings
from pathlib import Path

import numpy as np
import pytest
from clip import SAMPLE_RATE, clip

from dance_judge.analyze import analyze

EXPECTED = json.loads((Path(__file__).parent / "expected.json").read_text())


@pytest.fixture(scope="module")
def analysis():
    return analyze(clip(), SAMPLE_RATE)


def test_tempo_key_and_beats_match_exactly(analysis):
    assert analysis.tempo == EXPECTED["tempo"]
    assert (analysis.key, analysis.mode) == (EXPECTED["key"], EXPECTED["mode"])
    assert analysis.beats == pytest.approx(EXPECTED["beats"], rel=1e-12)
    assert analysis.duration == EXPECTED["duration"]


@pytest.mark.parametrize("name", EXPECTED["features"])
def test_feature_matches(analysis, name):
    # The two FFTs round differently in the last bits; nothing else should differ.
    assert analysis.features[name] == pytest.approx(EXPECTED["features"][name], rel=1e-9)


def test_envelope_matches(analysis):
    assert analysis.envelope == pytest.approx(EXPECTED["envelope"], abs=1e-9)


def test_the_clip_is_what_it_was_built_to_be(analysis):
    # 100 BPM (the grid allows 99.5), over an A minor chord.
    assert analysis.tempo == pytest.approx(100, abs=1)
    assert (analysis.key, analysis.mode) == (9, 0)


@pytest.mark.parametrize(
    "samples",
    [np.zeros(SAMPLE_RATE * 3, dtype=np.float32), clip()[:9000], clip()[:500]],
    ids=["silence", "under half a second", "shorter than one frame"],
)
def test_odd_clips_dont_break_it(samples):
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        analysis = analyze(samples, SAMPLE_RATE)
    assert all(np.isfinite(value) for value in analysis.features.values())
    assert len(analysis.envelope) == 240
