"""Turns a downloaded preview into the samples the analyzer wants."""

from __future__ import annotations

import io
import math

import av
import numpy as np

# 22.05 kHz is plenty for beats and keys, and it's the rate the scoring
# weights were calibrated at.
SAMPLE_RATE = 22050


class Unreadable(Exception):
    """The bytes weren't audio, or held none."""


def decode(data: bytes) -> np.ndarray:
    """Decodes any format FFmpeg knows to mono float samples at SAMPLE_RATE."""
    try:
        with av.open(io.BytesIO(data)) as container:
            resampler = av.AudioResampler(format="fltp", rate=SAMPLE_RATE)
            chunks = [out.to_ndarray() for frame in container.decode(audio=0) for out in resampler.resample(frame)]
            # A last call with nothing flushes what the resampler was holding.
            chunks += [out.to_ndarray() for out in resampler.resample(None)]
    except (av.FFmpegError, IndexError, ValueError) as error:
        raise Unreadable(str(error)) from error
    if not chunks:
        raise Unreadable("no audio in the file")
    channels = np.concatenate(chunks, axis=1)
    # Stereo is summed and divided by √2, not averaged. The weights were
    # calibrated on clips mixed that way (it's what macOS's afconvert does),
    # and an average would read 3 dB quieter and score lower on energy.
    return (channels.sum(axis=0) / math.sqrt(len(channels))).astype(np.float32)
