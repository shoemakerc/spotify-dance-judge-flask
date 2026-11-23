"""Turns what the analyzer heard into Spotify's old 0–1 scales, and those
into a verdict.

The weights are ridge regressions against Spotify's archived audio features
(as mirrored by ReccoBeats) for 295 songs, measured on the same 30-second
previews this app plays. They're fit by scripts/calibrate-dance-judge.mjs in
the shoemakerc.github.io repo, against the analyzer this one is a port of,
and copied from src/lib/dance-judge/judge.ts there. On songs held out of the
fit, danceability correlates with Spotify's at r = 0.79 (typically within
0.09) and energy at r = 0.79 (within 0.11).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .analyze import Analysis

INPUT_NAMES = [
    "pulse",
    "pulseLow",
    "stability",
    "log onBeat",
    "log offBeat",
    "percussive",
    "onsetRate",
    "log flux",
    "log airFlux",
    "bass",
    "crest",
    "loudness",
    "dynamics",
    "log centroid",
    "log flatness",
    "log brightness",
    "keyStrength",
    "major",
    "tempo octave",
    "tempo octave²",
]


def inputs(a: Analysis) -> list[float]:
    """The model inputs, in INPUT_NAMES order."""
    f = a.features
    octave = math.log2(a.tempo / 120)
    return [
        f["pulse"],
        f["pulseLow"],
        f["stability"],
        math.log(f["onBeat"] or 1),
        math.log(f["offBeat"] or 1),
        f["percussive"],
        f["onsetRate"],
        math.log(f["flux"] or 1e-3),
        math.log(f["airFlux"] or 1e-3),
        f["bass"],
        f["crest"],
        f["loudness"],
        f["dynamics"],
        math.log(f["centroid"] or 1),
        math.log(f["flatness"] or 1e-6),
        math.log(f["brightness"] or 1e-6),
        f["keyStrength"],
        a.mode,
        octave,
        octave * octave,
    ]


# Keep these in step with judge.ts; they change only when it's recalibrated.
DANCEABILITY = (
    0.096,
    [
        0.00338, 0.09491, -0.02825, 0.0707, -0.03045, 0.2291, -0.03508, 0.45168, 0.13936, 0.08968,
        -0.00932, 0.00167, 0.00227, 0.09151, -0.02232, 0.00668, 0.01248, 0.00404, -0.01137, -0.14844,
    ],
)  # fmt: skip

ENERGY = (
    -0.09529,
    [
        0.20594, 0.12045, -0.03593, 0.03755, -0.00162, 0.42856, -0.00396, 0.11153, -0.0776, 0.01965,
        -0.00807, 0.02, -0.01259, 0.18728, 0.05793, -0.03075, -0.19942, 0.00977, 0.01019, -0.19255,
    ],
)  # fmt: skip


def _score(model: tuple[float, list[float]], x: list[float]) -> float:
    intercept, coef = model
    return min(1.0, max(0.0, intercept + sum(c * xi for c, xi in zip(coef, x))))


# The 2017 verdicts, unchanged.
VERDICTS = [
    (0.25, "You’re gonna look silly dancing to this…"),
    (0.45, "You can try to dance to this, but it might look a bit weird."),
    (0.6, "Alright, I guess I’ll allow it."),
    (0.85, "I recommend you get down to this."),
    (math.inf, "A complete banger. I hope you’re busting moves right now."),
]

THRESHOLDS = [limit for limit, _ in VERDICTS[:-1]]
"""Where the verdicts change, for drawing the meter."""

# Below this beat strength the onsets barely repeat (ambient, rubato piano),
# and in calibration three in four tempo guesses down there were wrong.
STEADY_PULSE = 0.14

MAJOR_NAMES = ["C", "D♭", "D", "E♭", "E", "F", "F♯", "G", "A♭", "A", "B♭", "B"]
MINOR_NAMES = ["C", "C♯", "D", "E♭", "E", "F", "F♯", "G", "G♯", "A", "B♭", "B"]


@dataclass(frozen=True)
class Verdict:
    danceability: float
    energy: float
    line: str
    tempo: int | None
    """Beats per minute, or None when there's no steady beat to count."""
    key: str


def judge(a: Analysis) -> Verdict:
    x = inputs(a)
    danceability = _score(DANCEABILITY, x)
    return Verdict(
        danceability=danceability,
        energy=_score(ENERGY, x),
        line=next(line for limit, line in VERDICTS if danceability < limit),
        tempo=math.floor(a.tempo + 0.5) if a.features["pulse"] >= STEADY_PULSE else None,
        key=f"{(MAJOR_NAMES if a.mode else MINOR_NAMES)[a.key]} {'major' if a.mode else 'minor'}",
    )
