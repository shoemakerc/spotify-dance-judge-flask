"""Listens to a short clip and measures what the 2017 Dance Judge used to ask
Spotify for: how strong and steady the beat is, how fast it goes, what key
it's in, and how loud and bright it sounds.

This is a NumPy port of the analyzer behind the browser version at
shoemakerc.github.io/dance-judge (src/lib/dance-judge/analyze.ts there). The
scoring weights in verdict.py were fit to that analyzer's numbers, so this one
has to produce the same numbers: tests/test_analyze.py holds it to that.
Where the two could drift (rounding halves, loops that accumulate a float)
the code follows the original on purpose, and says so.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

ENVELOPE_POINTS = 240
MEL_BANDS = 40
LOW_HZ = 160
AIR_HZ = 2000


@dataclass(frozen=True)
class Analysis:
    tempo: float
    """Beats per minute."""
    key: int
    """Pitch class of the tonic, 0 = C."""
    mode: int
    """1 for major, 0 for minor."""
    features: dict[str, float]
    envelope: list[float]
    """Onset strength over the clip, 0–1, for drawing."""
    beats: list[float]
    """Beat times in seconds."""
    duration: float
    """Clip length in seconds."""


def analyze(samples: np.ndarray, sample_rate: int) -> Analysis:
    """Analyzes mono samples in the range −1 to 1."""
    samples = np.asarray(samples, dtype=np.float64)
    rhythm = _rhythm_frames(samples, sample_rate)
    onset, fps = rhythm["onset"], rhythm["fps"]

    acf = _autocorrelate(onset, math.ceil(fps * 2.6))
    tempo = _pick_tempo(acf, fps)
    period = 60 * fps / tempo

    pulse = max(0.0, float(_at(acf, 60 * fps / np.arange(60, 180.25, 0.5)).max()))
    acf_low = _autocorrelate(rhythm["onset_low"], math.ceil(period * 1.1))

    peaks = _local_maxima(onset)
    phase = _beat_phase(peaks, len(onset), period)
    key = estimate_key(samples, sample_rate)

    features = {
        # How periodic the onsets are at the strongest beat lag (0–1).
        "pulse": pulse,
        # The same, for the kick-drum range only.
        "pulseLow": _peak_near(acf_low, period),
        # Average periodicity at the chosen tempo over 6-second windows (0–1).
        "stability": _local_stability(onset, period, fps),
        # Onset strength on the beat, and halfway between beats, relative to the average.
        "onBeat": _grid_strength(onset, peaks, phase, period),
        "offBeat": _grid_strength(onset, peaks, phase + period / 2, period),
        # Share of the energy that's percussive rather than sustained (0–1).
        "percussive": rhythm["percussive"],
        # Onsets per second.
        "onsetRate": _count_onsets(onset, fps) / (len(onset) / fps),
        # Average onset strength in dB per frame; then the same above 2 kHz.
        "flux": rhythm["flux"],
        "airFlux": rhythm["air_flux"],
        # Share of the energy below 150 Hz.
        "bass": rhythm["bass"],
        # Peak-to-average level in dB; low when squashed loud.
        "crest": _crest_factor(samples, sample_rate),
        # K-weighted loudness in dB, gated like EBU R128 (roughly LUFS).
        "loudness": rhythm["loudness"],
        # Spread between loud and quiet passages, in dB.
        "dynamics": rhythm["dynamics"],
        # Spectral centroid in Hz, flatness (0 tonal, 1 noise), share above 4 kHz.
        "centroid": rhythm["centroid"],
        "flatness": rhythm["flatness"],
        "brightness": rhythm["brightness"],
        # How well the clip fits its best key profile (correlation, −1–1).
        "keyStrength": key["strength"],
    }

    return Analysis(
        tempo=tempo,
        key=key["tonic"],
        mode=key["mode"],
        features=features,
        envelope=_downsample(onset, ENVELOPE_POINTS),
        beats=[t / fps for t in _grid(phase, period, len(onset))],
        duration=len(samples) / sample_rate,
    )


def _js_round(x: float) -> int:
    """Rounds halves up, as JavaScript's Math.round does. Python's round()
    sends halves to the even neighbor, which would pick a different frame."""
    return math.floor(x + 0.5)


# ---------- Spectra ----------


def _power_frames(samples: np.ndarray, n: int, hop: int, frames: int):
    """The frames themselves, and the power spectrum (n/2 + 1 bins) of each
    under a Hann window. A last frame that runs past the end is zero-padded."""
    need = (frames - 1) * hop + n
    if len(samples) < need:
        samples = np.concatenate([samples, np.zeros(need - len(samples))])
    framed = sliding_window_view(samples[:need], n)[::hop]
    window = 0.5 - 0.5 * np.cos(2 * np.pi * np.arange(n) / n)
    spectrum = np.fft.rfft(framed * window, axis=1)
    return framed, spectrum.real**2 + spectrum.imag**2


def _hz_to_mel(f: float) -> float:
    return 2595 * math.log10(1 + f / 700)


def _mel_to_hz(m: float) -> float:
    return 700 * (10 ** (m / 2595) - 1)


def _mel_bands(n: int, sample_rate: int, count: int, f_min: float, f_max: float):
    """Triangular filters as a (count, n/2 + 1) matrix, and their center frequencies."""
    bin_hz = sample_rate / n
    lo_mel, hi_mel = _hz_to_mel(f_min), _hz_to_mel(f_max)
    edges = [_mel_to_hz(lo_mel + (hi_mel - lo_mel) * i / (count + 1)) for i in range(count + 2)]
    bank = np.zeros((count, n // 2 + 1))
    for b in range(count):
        left, center, right = edges[b], edges[b + 1], edges[b + 2]
        lo = max(1, math.floor(left / bin_hz))
        hi = min(n // 2, math.ceil(right / bin_hz))
        f = np.arange(lo, hi + 1) * bin_hz
        weights = np.maximum(0, np.where(f <= center, (f - left) / (center - left), (right - f) / (right - center)))
        if not weights.any():
            # Very low bands can be narrower than one bin; give them the nearest one.
            weights = np.zeros(max(1, hi - lo + 1))
            weights[min(len(weights) - 1, _js_round(center / bin_hz) - lo)] = 1
        bank[b, lo : lo + len(weights)] = weights
    return bank, edges[1:-1]


# ---------- Rhythm ----------


def _rhythm_frames(samples: np.ndarray, sample_rate: int) -> dict:
    """One pass over the clip in ~46 ms frames: an onset-strength envelope
    (how much new sound arrives in each frame), the same for the bass range,
    and the loudness and timbre numbers."""
    n = 2 ** _js_round(math.log2(sample_rate * 0.046))
    hop = n // 4
    fps = sample_rate / hop
    frames = max(1, (len(samples) - n) // hop + 1)
    framed, power = _power_frames(samples, n, hop, frames)
    bank, centers = _mel_bands(n, sample_rate, MEL_BANDS, 30, min(11000, sample_rate / 2))
    low = sum(c < LOW_HZ for c in centers)
    air = next((i for i, c in enumerate(centers) if c >= AIR_HZ), -1)
    bin_hz = sample_rate / n
    hf_bin = math.ceil(4000 / bin_hz)
    bass_bin = math.floor(150 / bin_hz)

    # Everything but the DC bin.
    p = power[:, 1:]
    f = np.arange(1, n // 2 + 1) * bin_hz
    # The K-weighting curve loudness meters use: roll off the deep bass, lift
    # the presence range a few dB, the way ears do.
    k_weight = (f**4 / (f**4 + 38**4)) * (1 + (10**0.4 - 1) * f * f / (f * f + 1500**2))

    total = p.sum(axis=1)
    sounding = total > 0
    safe = np.where(sounding, total, 1)
    centroid = np.where(sounding, (p * f).sum(axis=1) / safe, 0)
    brightness = np.where(sounding, p[:, hf_bin - 1 :].sum(axis=1) / safe, 0)
    bass = np.where(sounding, p[:, :bass_bin].sum(axis=1) / safe, 0)
    geometric = np.exp(np.log(p + 1e-12).sum(axis=1) / (n / 2))
    flatness = np.where(sounding, geometric / (safe / (n / 2)), 0)
    # Mean square of the frame, by Parseval (one-sided spectrum, Hann window).
    heard = (p * k_weight).sum(axis=1) * 16 / (3 * n * n)
    frame_db = 10 * np.log10((framed**2).sum(axis=1) / n + 1e-12)
    mel = power @ bank.T

    # Ignore near-silence (fades, gaps) in the loudness and timbre averages.
    active = frame_db > frame_db.max() - 50
    # Loudness meters gate out anything 20 dB below the loudest passages.
    heard_db = 10 * np.log10(heard + 1e-12)
    gated = heard_db[heard_db > heard_db.max() - 20]
    mean_heard = (10 ** (gated / 10)).mean()
    sorted_db = np.sort(frame_db[active])

    # Onset strength: rises in log band energy, averaged across bands.
    db = 10 * np.log10(mel + 1e-10)
    db = np.maximum(db, db.max() - 80)
    rise = np.maximum(0, np.diff(db, axis=0))
    onset = np.zeros(frames)
    onset_low = np.zeros(frames)
    onset[1:] = rise.sum(axis=1) / MEL_BANDS
    onset_low[1:] = rise[:, :low].sum(axis=1) / max(1, low)
    # With no band above AIR_HZ the original's test (b >= -1) lets every band in.
    air_rise = rise[:, max(air, 0) :].sum()

    return {
        "onset": onset,
        "onset_low": onset_low,
        "fps": fps,
        "flux": float(onset.sum() / frames),
        "air_flux": float(air_rise / frames / (MEL_BANDS - air)),
        "bass": float(bass[active].mean()),
        "percussive": _percussive_share(mel),
        "loudness": float(10 * np.log10(mean_heard + 1e-12)),
        "dynamics": float(_percentile(sorted_db, 0.95) - _percentile(sorted_db, 0.1)),
        "centroid": float(centroid[active].mean()),
        "flatness": float(flatness[active].mean()),
        "brightness": float(brightness[active].mean()),
    }


def _edge_median(values: np.ndarray, span: int, axis: int) -> np.ndarray:
    """Median over `span` neighbors each side along an axis; windows shrink at the edges."""
    pad = [(0, 0)] * values.ndim
    pad[axis] = (span, span)
    padded = np.pad(values, pad, constant_values=np.nan)
    return np.nanmedian(sliding_window_view(padded, 2 * span + 1, axis=axis), axis=-1)


def _percussive_share(mel: np.ndarray) -> float:
    """Harmonic/percussive split by median filtering (Fitzgerald 2010), on
    the mel spectrogram to keep it cheap: sustained notes are smooth across
    time, hits are smooth across frequency."""
    harmonic = _edge_median(mel, 8, axis=0)
    percussive = _edge_median(mel, 4, axis=1)
    both = harmonic**2 + percussive**2
    mask = np.where(harmonic + percussive > 0, percussive**2 / np.where(both > 0, both, 1), 0)
    total = mel.sum()
    return float((mask * mel).sum() / total) if total > 0 else 0.0


def _crest_factor(samples: np.ndarray, sample_rate: int) -> float:
    seconds = len(samples) // sample_rate
    if not seconds:
        return 0.0
    chunks = samples[: seconds * sample_rate].reshape(seconds, sample_rate)
    energy = (chunks**2).sum(axis=1)
    loud = energy > 0
    if not loud.any():
        return 0.0
    peak = np.abs(chunks[loud]).max(axis=1)
    return float(np.median(20 * np.log10(peak / np.sqrt(energy[loud] / sample_rate))))


def _autocorrelate(x: np.ndarray, max_lag: int) -> np.ndarray:
    """Normalized autocorrelation of the mean-removed signal, lags 0..max_lag."""
    n = len(x)
    d = x - x.mean()
    r = np.zeros(min(max_lag, n - 1) + 1)
    zero = d @ d
    if zero == 0:
        return r
    for lag in range(len(r)):
        # Unbiased: don't penalize long lags for having fewer overlapping frames.
        r[lag] = (d[: n - lag] @ d[lag:]) / zero * (n / (n - lag))
    return r


def _at(xs: np.ndarray, i):
    """Linear interpolation into an array at fractional indexes; 0 outside it."""
    i = np.asarray(i, dtype=np.float64)
    lo = np.floor(i).astype(int)
    inside = (lo >= 0) & (lo + 1 < len(xs))
    lo = np.where(inside, lo, 0)
    hi = np.minimum(lo + 1, len(xs) - 1)
    return np.where(inside, xs[lo] + (xs[hi] - xs[lo]) * (i - lo), 0.0)


def _peak_near(acf: np.ndarray, lag: float) -> float:
    lags = []
    position = lag * 0.96
    # Stepped by repeated addition, as the original does, so the last step lands the same.
    while position <= lag * 1.04:
        lags.append(position)
        position += 0.25
    return max(0.0, float(_at(acf, lags).max())) if lags else 0.0


def _pick_tempo(acf: np.ndarray, fps: float) -> float:
    """Strongest periodicity between 55 and 215 BPM, weighted toward ~120 the
    way listeners tap along (a log-normal prior, as in librosa's beat
    tracker), and checked against the half and double tempo so a busy hi-hat
    doesn't win."""
    bpm = np.arange(55, 215.25, 0.25)
    lag = 60 * fps / bpm
    r = _at(acf, lag) + 0.5 * _at(acf, lag * 2) + 0.25 * _at(acf, lag / 2)
    prior = -0.5 * (np.log2(bpm / 120) / 0.9) ** 2
    best = float(bpm[np.argmax(np.log(np.maximum(r, 1e-4)) + prior)])
    return _js_round(best * 10) / 10


def _grid(phase: float, period: float, length: int) -> list[float]:
    """Beat positions in frames from `phase` on. Built by repeated addition:
    phase + k * period can differ in the last bit, and near a half that
    changes which frame a beat rounds to."""
    out = []
    t = phase
    while t < length:
        out.append(t)
        t += period
    return out


def _local_maxima(onset: np.ndarray) -> np.ndarray:
    """For each frame c from 0 to len(onset), the largest onset among c − 1, c and c + 1."""
    padded = np.concatenate([[0.0], onset, [0.0, 0.0]])
    return sliding_window_view(padded, 3).max(axis=1)


def _beat_phase(peaks: np.ndarray, length: int, period: float) -> float:
    """The offset (in frames) of the beat grid that lines up with the most onsets."""
    best, best_sum = 0.0, -math.inf
    phase = 0.0
    while phase < period:
        total = sum(peaks[_js_round(t)] for t in _grid(phase, period, length))
        if total > best_sum:
            best, best_sum = phase, total
        phase += 0.5
    return best


def _grid_strength(onset: np.ndarray, peaks: np.ndarray, phase: float, period: float) -> float:
    mean = onset.mean()
    grid = _grid(phase, period, len(onset))
    if mean == 0 or not grid:
        return 0.0
    return float(sum(peaks[_js_round(t)] for t in grid) / len(grid) / mean)


def _local_stability(onset: np.ndarray, period: float, fps: float) -> float:
    size = _js_round(6 * fps)
    hop = _js_round(1.5 * fps)
    max_lag = math.ceil(period * 1.1)
    if len(onset) <= size:
        return _peak_near(_autocorrelate(onset, max_lag), period)
    strengths = [
        _peak_near(_autocorrelate(onset[start : start + size], max_lag), period)
        for start in range(0, len(onset) - size + 1, hop)
    ]
    return sum(strengths) / len(strengths)


def _count_onsets(onset: np.ndarray, fps: float) -> int:
    threshold = onset.mean() + 0.5 * onset.std()
    gap = _js_round(0.05 * fps)
    middle = onset[1:-1]
    candidates = np.flatnonzero((middle > threshold) & (middle >= onset[:-2]) & (middle > onset[2:])) + 1
    count, last = 0, -math.inf
    for t in candidates:
        if t - last >= gap:
            count += 1
            last = t
    return count


# ---------- Key ----------

# Temperley's key profiles ("What's Key for Key?", 1999), from the tonic up,
# with the flat seventh raised: pop leans on it (Mixolydian riffs, natural
# minor) far more than the classical music the profiles came from. On 42
# songs with well-known keys this named 32 right, to 23 for the original
# profiles and 20 for Spotify's own key data.
MAJOR = [5, 2, 3.5, 2, 4.5, 4, 2, 4.5, 2, 3.5, 2.5, 4]
MINOR = [5, 2, 3.5, 4.5, 2, 4, 2, 4.5, 3.5, 2, 3.5, 2.5]


def estimate_key(samples: np.ndarray, sample_rate: int) -> dict:
    """A pitch-class histogram from spectral peaks between 80 Hz and 1.5 kHz
    (the fundamentals, mostly, rather than their overtones) in ~370 ms
    frames, matched against the 24 major and minor key profiles."""
    samples = np.asarray(samples, dtype=np.float64)
    n = 2 ** _js_round(math.log2(sample_rate * 0.37))
    hop = n // 2
    bin_hz = sample_rate / n
    lo = math.ceil(80 / bin_hz)
    hi = min(n // 2 - 1, math.floor(1500 / bin_hz))
    chroma = np.zeros(12)

    frames = (len(samples) - n) // hop + 1 if len(samples) >= n else 0
    spectra = _power_frames(samples, n, hop, frames)[1] if frames else []
    for power in spectra:
        k = np.arange(lo, hi + 1)
        m = power[k]
        peak = m.max()
        if peak == 0:
            continue
        is_peak = (m >= peak * 1e-4) & (m > power[k - 1]) & (m >= power[k + 1])
        k, m = k[is_peak], m[is_peak]
        # Parabolic interpolation on log power for the true peak frequency.
        a, b, c = np.log(power[k - 1] + 1e-12), np.log(m), np.log(power[k + 1] + 1e-12)
        curve = a - 2 * b + c
        offset = np.where(curve == 0, 0, 0.5 * (a - c) / np.where(curve == 0, 1, curve))
        midi = 69 + 12 * np.log2((k + offset) * bin_hz / 440)
        nearest = np.floor(midi + 0.5)
        cents = np.abs(midi - nearest)
        in_tune = cents <= 0.4
        frame = np.bincount(
            nearest[in_tune].astype(int) % 12,
            weights=(np.sqrt(m) * (1 - cents / 0.4))[in_tune],
            minlength=12,
        )
        if frame.sum() > 0:
            chroma += frame / frame.sum()

    best = {"tonic": 0, "mode": 1, "strength": -1.0}
    for tonic in range(12):
        for mode, profile in ((1, MAJOR), (0, MINOR)):
            rotated = [profile[(i - tonic) % 12] for i in range(12)]
            strength = _correlation(chroma, np.array(rotated))
            if strength > best["strength"]:
                best = {"tonic": tonic, "mode": mode, "strength": strength}
    return best


# ---------- Helpers ----------


def _correlation(a: np.ndarray, b: np.ndarray) -> float:
    da, db = a - a.mean(), b - b.mean()
    spread = (da @ da) * (db @ db)
    return float(da @ db / math.sqrt(spread)) if spread else 0.0


def _percentile(ordered: np.ndarray, q: float) -> float:
    if not len(ordered):
        return 0.0
    return float(ordered[min(len(ordered) - 1, max(0, _js_round(q * (len(ordered) - 1))))])


def _downsample(xs: np.ndarray, points: int) -> list[float]:
    size = len(xs) / points
    out = []
    for i in range(points):
        chunk = xs[math.floor(i * size) : min(len(xs), math.floor((i + 1) * size))]
        out.append(max(0.0, float(chunk.max())) if len(chunk) else 0.0)
    top = _percentile(np.sort(out), 0.98) or 1
    return [_js_round(min(1, x / top) * 1000) / 1000 for x in out]
