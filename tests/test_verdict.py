import pytest
from clip import SAMPLE_RATE, clip

from dance_judge import verdict as verdicts
from dance_judge.analyze import Analysis, analyze
from dance_judge.verdict import DANCEABILITY, ENERGY, INPUT_NAMES, VERDICTS, inputs, judge


def test_weights_line_up_with_inputs():
    analysis = analyze(clip(), SAMPLE_RATE)
    assert len(inputs(analysis)) == len(INPUT_NAMES) == len(DANCEABILITY[1]) == len(ENERGY[1])


def test_a_steady_beat_is_judged():
    verdict = judge(analyze(clip(), SAMPLE_RATE))
    assert 0 <= verdict.danceability <= 1 and 0 <= verdict.energy <= 1
    assert verdict.tempo == 100
    assert verdict.key == "A minor"
    assert verdict.line in [line for _, line in VERDICTS]


@pytest.mark.parametrize(
    ("danceability", "line"),
    [
        (0.0, "You’re gonna look silly dancing to this…"),
        (0.25, "You can try to dance to this, but it might look a bit weird."),
        (0.59, "Alright, I guess I’ll allow it."),
        (0.6, "I recommend you get down to this."),
        (1.0, "A complete banger. I hope you’re busting moves right now."),
    ],
)
def test_the_2017_verdicts(monkeypatch, danceability, line):
    monkeypatch.setattr(verdicts, "_score", lambda model, x: danceability)
    assert judge(analyze(clip(), SAMPLE_RATE)).line == line


def test_no_tempo_without_a_steady_beat():
    real = analyze(clip(), SAMPLE_RATE)
    drifting = Analysis(**{**real.__dict__, "features": {**real.features, "pulse": 0.1}})
    assert judge(drifting).tempo is None


def test_flat_keys_use_the_flat_sign():
    real = analyze(clip(), SAMPLE_RATE)
    assert judge(Analysis(**{**real.__dict__, "key": 10, "mode": 1})).key == "B♭ major"
    assert judge(Analysis(**{**real.__dict__, "key": 1, "mode": 0})).key == "C♯ minor"
