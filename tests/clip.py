"""A ten-second test clip made with whole-number arithmetic only, so that
make_expected.mjs builds exactly the same samples in JavaScript: a held
chord of triangle waves, a noise burst on each beat at 100 BPM, and a
quieter one between beats."""

import numpy as np

SAMPLE_RATE = 22050
SECONDS = 10


def clip() -> np.ndarray:
    state = 12345
    out = np.empty(SAMPLE_RATE * SECONDS, dtype=np.float32)

    def noise() -> int:
        nonlocal state
        state = (state * 1664525 + 1013904223) & 0xFFFFFFFF
        return ((state >> 16) & 0xFFFF) - 32768

    for i in range(len(out)):
        chord = sum((abs((i % p) * 2 - p) * 2 - p) * 2000 // p for p in (100, 84, 67))
        beat = i % 13230
        half = i % 6615
        hit = noise() * (1500 - beat) // 1500 // 2 if beat < 1500 else 0
        hat = noise() * (300 - half) // 300 // 8 if half < 300 and beat >= 1500 else 0
        out[i] = max(-32768, min(32767, chord + hit + hat)) / 32768
    return out
