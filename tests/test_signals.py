import numpy as np

from assessor.media import ANALYSIS_SR as AUDIO_SR
from assessor.signals import analyse_audio, analyse_visual


def _tone(seconds, amp=0.3, f=220):
    t = np.arange(int(seconds * AUDIO_SR)) / AUDIO_SR
    # amplitude-modulated tone ~ syllable rhythm
    return (amp * np.sin(2 * np.pi * f * t) * (0.6 + 0.4 * np.sin(2 * np.pi * 4 * t))).astype(np.float32)


def _noise(seconds, amp=0.003):
    rng = np.random.default_rng(0)
    return (amp * rng.standard_normal(int(seconds * AUDIO_SR))).astype(np.float32)


def test_detects_long_silence():
    audio = np.concatenate([_tone(30), _noise(20), _tone(30), _noise(4), _tone(16)])
    s = analyse_audio(audio)
    assert 19 <= s.longest_silence_s <= 21
    assert s.silences_over_10s == 1
    assert 0.7 < s.speech_ratio < 0.85
    assert s.snr_db > 20


def test_all_speech():
    s = analyse_audio(_tone(60))
    assert s.speech_ratio > 0.95 and s.longest_silence_s == 0


def test_visual_static_and_changes():
    static = np.full((30, 36, 64), 120, dtype=np.uint8)
    v = analyse_visual(static, 2.0)
    assert v.static_ratio == 1.0 and v.screen_changes_per_min == 0
    slides = np.concatenate([np.full((10, 36, 64), c, dtype=np.uint8) for c in (40, 120, 200)])
    v = analyse_visual(slides, 2.0)
    assert v.screen_changes_per_min > 0 and v.black_ratio == 0
