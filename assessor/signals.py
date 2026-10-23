"""Objective, model-free signals measured directly from the recording.

These are deliberately simple and explainable. They are used (a) as context for the
LLM so its judgement is grounded in measurements, and (b) for small, transparent
adjustments to the final score. Several of them can mislead (e.g. silence may be
students working on a task), so they never decide the rating on their own.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

import numpy as np

from .media import ANALYSIS_SR as AUDIO_SR

FRAME_S = 0.03  # 30 ms analysis frames


def fmt_ts(seconds: float) -> str:
    seconds = max(0, int(round(seconds)))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


@dataclass
class AudioSignals:
    duration_s: float
    speech_ratio: float            # fraction of the class with someone speaking
    longest_silence_s: float
    silences_over_10s: int
    silence_spans: list[tuple[float, float]] = field(default_factory=list)  # (start, end), longest first
    speech_level_dbfs: float = -99.0  # median loudness while speaking
    snr_db: float = 0.0            # speech level vs background noise floor
    clipping_ratio: float = 0.0    # fraction of samples at/near full scale
    loudness_variation_db: float = 0.0  # spread of speech loudness (monotone vs lively)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["silence_spans"] = [[fmt_ts(a), fmt_ts(b)] for a, b in self.silence_spans]
        return d


@dataclass
class VisualSignals:
    sampled_every_s: float
    screen_changes_per_min: float  # how often the shared screen/scene noticeably changes
    static_ratio: float            # fraction of samples with essentially no change
    black_ratio: float             # fraction of near-black frames (camera off / blank)
    longest_static_s: float

    def to_dict(self) -> dict:
        return asdict(self)


def _frame_db(audio: np.ndarray) -> np.ndarray:
    n = int(AUDIO_SR * FRAME_S)
    usable = len(audio) // n * n
    if usable == 0:
        return np.full(1, -99.0)
    frames = audio[:usable].reshape(-1, n)
    rms = np.sqrt(np.mean(frames ** 2, axis=1) + 1e-12)
    return 20 * np.log10(rms + 1e-9)


def _smooth_bool(mask: np.ndarray, min_run: int) -> np.ndarray:
    """Remove runs of False shorter than min_run (bridges short pauses between words)."""
    out = mask.copy()
    i, n = 0, len(mask)
    while i < n:
        if not out[i]:
            j = i
            while j < n and not out[j]:
                j += 1
            if j - i < min_run and i > 0 and j < n:
                out[i:j] = True
            i = j
        else:
            i += 1
    return out


def _runs(mask: np.ndarray, value: bool) -> list[tuple[int, int]]:
    runs, start = [], None
    for i, v in enumerate(mask):
        if v == value and start is None:
            start = i
        elif v != value and start is not None:
            runs.append((start, i))
            start = None
    if start is not None:
        runs.append((start, len(mask)))
    return runs


def analyse_audio(audio: np.ndarray) -> AudioSignals:
    duration = len(audio) / AUDIO_SR
    db = _frame_db(audio)
    noise_floor = float(np.percentile(db, 10))
    loud = float(np.percentile(db, 95))
    # Adaptive threshold between the noise floor and the loud speech level.
    thresh = max(noise_floor + 0.35 * (loud - noise_floor), -55.0)
    speech = db > thresh
    speech = _smooth_bool(speech, min_run=int(0.6 / FRAME_S))  # pauses < 0.6 s are within speech

    silence_runs = [(a * FRAME_S, b * FRAME_S) for a, b in _runs(speech, False)]
    silence_runs = [(a, b) for a, b in silence_runs if b - a >= 3.0]
    silence_runs.sort(key=lambda r: r[1] - r[0], reverse=True)
    longest = silence_runs[0][1] - silence_runs[0][0] if silence_runs else 0.0

    speech_db = db[speech] if speech.any() else db
    return AudioSignals(
        duration_s=round(duration, 1),
        speech_ratio=round(float(speech.mean()), 3),
        longest_silence_s=round(longest, 1),
        silences_over_10s=sum(1 for a, b in silence_runs if b - a >= 10),
        silence_spans=silence_runs[:8],
        speech_level_dbfs=round(float(np.median(speech_db)), 1),
        snr_db=round(float(np.median(speech_db) - noise_floor), 1),
        clipping_ratio=round(float(np.mean(np.abs(audio) > 0.99)) if len(audio) else 0.0, 5),
        loudness_variation_db=round(float(np.std(speech_db)), 1),
    )


def analyse_visual(frames: np.ndarray, every_s: float) -> VisualSignals | None:
    if len(frames) < 3:
        return None
    f = frames.astype(np.float32)
    diffs = np.mean(np.abs(np.diff(f, axis=0)), axis=(1, 2))  # mean abs pixel change, 0..255
    changes = diffs > 12.0          # a noticeable slide/scene change
    static = diffs < 1.5            # practically frozen screen
    black = np.mean(f, axis=(1, 2)) < 12
    minutes = len(frames) * every_s / 60
    static_runs = _runs(static, True)
    longest_static = max((b - a for a, b in static_runs), default=0) * every_s
    return VisualSignals(
        sampled_every_s=every_s,
        screen_changes_per_min=round(float(changes.sum() / max(minutes, 1e-6)), 2),
        static_ratio=round(float(static.mean()), 3),
        black_ratio=round(float(black.mean()), 3),
        longest_static_s=round(float(longest_static), 1),
    )
