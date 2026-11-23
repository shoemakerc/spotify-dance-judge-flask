import io
import math
import wave

import numpy as np
import pytest

from dance_judge.audio import SAMPLE_RATE, Unreadable, decode


def wav(channels: list[np.ndarray], rate: int) -> bytes:
    """A 16-bit WAV file in memory."""
    out = io.BytesIO()
    with wave.open(out, "wb") as f:
        f.setnchannels(len(channels))
        f.setsampwidth(2)
        f.setframerate(rate)
        f.writeframes((np.stack(channels, axis=1) * 32767).astype("<i2").tobytes())
    return out.getvalue()


def tone(rate: int, seconds: float = 1.0) -> np.ndarray:
    return 0.25 * np.sin(2 * np.pi * 440 * np.arange(int(rate * seconds)) / rate)


def rms(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(x, dtype=np.float64))))


def test_mono_comes_through_at_the_analysis_rate():
    samples = decode(wav([tone(44100)], 44100))
    assert samples.dtype == np.float32
    assert len(samples) == pytest.approx(SAMPLE_RATE, abs=64)
    assert rms(samples) == pytest.approx(0.25 / math.sqrt(2), rel=0.02)


def test_stereo_is_summed_over_root_two_not_averaged():
    # Calibration mixed stereo this way; averaging would read 3 dB quieter.
    left = tone(SAMPLE_RATE)
    samples = decode(wav([left, left], SAMPLE_RATE))
    assert rms(samples) == pytest.approx(rms(left) * math.sqrt(2), rel=0.02)


def test_garbage_is_unreadable():
    with pytest.raises(Unreadable):
        decode(b"not audio at all")
