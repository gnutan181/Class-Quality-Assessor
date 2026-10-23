"""The quality rubric and the deterministic scoring that turns it into a label.

The LLM scores each dimension 1-4 with timestamped evidence. The final label is
computed here, not by the LLM, so it is reproducible, explainable and tunable on
the labelled samples (see calibrate.py, which writes calibration.json).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

LABELS = ["Poor", "Average", "Good", "Excellent"]

# Dimensions follow what 8x8's own reviewers comment on in their feedback on the
# sample classes: rapport/intro, individual attention, energy, homework/closure,
# the 8x8 background and tutor camera, and technical quality.
# key -> (display name, weight, what the model should look for)
DIMENSIONS: dict[str, tuple[str, float, str]] = {
    "individual_attention": (
        "Individual attention & participation", 0.22,
        "Tutor calls on children one by one by name, makes sure every child (including quiet "
        "ones and new joiners) speaks and is asked questions; the class is a dialogue, not a "
        "monologue."),
    "rapport_intro": (
        "Rapport building & introduction", 0.18,
        "Warm greeting, small talk and rapport before the lesson, a clear introduction of "
        "the topic, and time for new joiners to introduce themselves. Jumping straight into "
        "revision or content without rapport is a weakness."),
    "energy_warmth": (
        "Energy & pleasant interaction", 0.16,
        "Energetic, cheerful, encouraging voice; specific praise; children sound comfortable "
        "and happy. Flat, monotone or impatient delivery is a weakness."),
    "teaching_clarity": (
        "Teaching clarity & activities", 0.16,
        "Concepts explained clearly at the children's level with examples, puzzles, games or "
        "topic-related videos; correct content; checks that children understood."),
    "closure_homework": (
        "Conclusion & homework", 0.10,
        "A recap/conclusion at the end and homework (HW) given and explained."),
    "presence_setup": (
        "Tutor presence & 8x8 setup", 0.10,
        "Tutor camera on throughout with face clearly visible and well lit; the 8x8 branded "
        "virtual background is used; a tidy, professional setup."),
    "av_quality": (
        "Audio/video quality", 0.08,
        "Clear audio and video with few interruptions; children are not repeatedly unable to "
        "hear or see; no persistent lag, echo or dropouts."),
}

assert abs(sum(w for _, w, _ in DIMENSIONS.values()) - 1.0) < 1e-9

DEFAULT_THRESHOLDS = [1.9, 2.6, 3.3]  # score <1.9 Poor, <2.6 Average, <3.3 Good, else Excellent
CALIBRATION_FILE = Path(__file__).resolve().parent.parent / "calibration.json"


def load_thresholds(path: Path = CALIBRATION_FILE) -> list[float]:
    try:
        t = json.loads(path.read_text())["thresholds"]
        if len(t) == 3 and t[0] < t[1] < t[2]:
            return [float(x) for x in t]
    except (OSError, KeyError, ValueError, TypeError):
        pass
    return list(DEFAULT_THRESHOLDS)


def label_for(score: float, thresholds: list[float]) -> str:
    for label, cut in zip(LABELS, thresholds):
        if score < cut:
            return label
    return LABELS[-1]


@dataclass
class Adjustment:
    reason: str
    delta: float


def signal_adjustments(audio: dict | None, visual: dict | None,
                       talk: dict | None = None) -> list[Adjustment]:
    """Small, capped nudges from measured signals. Kept modest on purpose: the
    measurements are noisy proxies, the evidence-based rubric does the real work."""
    adj: list[Adjustment] = []
    if audio:
        if audio["speech_ratio"] < 0.45:
            adj.append(Adjustment(
                f"Only {audio['speech_ratio']:.0%} of the recording contains speech", -0.15))
        if audio["clipping_ratio"] > 0.002:
            adj.append(Adjustment("Audio is distorted (clipping)", -0.05))
    if visual and visual["black_ratio"] > 0.5:
        adj.append(Adjustment("Video is blank/black for most of the class", -0.1))
    if talk and not talk["homework_mentioned"]:
        adj.append(Adjustment("No homework mentioned in the transcript", -0.05))
    total = sum(a.delta for a in adj)
    if total < -0.3:  # cap the total penalty
        scale = -0.3 / total
        adj = [Adjustment(a.reason, round(a.delta * scale, 3)) for a in adj]
    return adj


# Measured interaction from the Zoom transcript. On the 10 labelled samples these two
# numbers separated the levels better than anything else we measured: Excellent classes
# had a longest tutor monologue of ~45-55 s and 12-15 speaker switches a minute; Average
# and Weak classes had 130-450 s monologues and mostly 3-6 switches a minute.
MONOLOGUE_CUTS = [(60, 4), (120, 3), (180, 2)]   # longest tutor monologue (s) -> score
SWITCH_CUTS = [(12, 4), (7, 3), (4, 2)]          # speaker switches per minute -> score
TRANSCRIPT_WEIGHT = 0.2


def interaction_score(talk: dict) -> float:
    mono = talk["longest_teacher_monologue_s"]
    sw = talk["speaker_switches_per_min"]
    m = next((sc for cut, sc in MONOLOGUE_CUTS if mono < cut), 1)
    w = next((sc for cut, sc in SWITCH_CUTS if sw >= cut), 1)
    return (m + w) / 2


def weighted_score(dimension_scores: dict[str, float]) -> float:
    used = {k: v for k, v in dimension_scores.items() if k in DIMENSIONS and v is not None}
    if not used:
        raise ValueError("no dimension scores")
    wsum = sum(DIMENSIONS[k][1] for k in used)
    return sum(DIMENSIONS[k][1] * v for k, v in used.items()) / wsum


def final_rating(dimension_scores: dict[str, float], model_label: str | None,
                 audio: dict | None, visual: dict | None,
                 thresholds: list[float] | None = None, talk: dict | None = None) -> dict:
    thresholds = thresholds or load_thresholds()
    base = weighted_score(dimension_scores)
    measured = interaction_score(talk) if talk else None
    blended = base if measured is None else (1 - TRANSCRIPT_WEIGHT) * base + TRANSCRIPT_WEIGHT * measured
    adjustments = signal_adjustments(audio, visual, talk)
    score = min(4.0, max(1.0, blended + sum(a.delta for a in adjustments)))
    label = label_for(score, thresholds)

    # Confidence: lower when the score sits near a boundary or the model's holistic
    # judgement disagrees with the rubric-derived label.
    margin = min(abs(score - t) for t in thresholds)
    confidence = 0.55 + min(margin, 0.4)
    agreement = None
    if model_label in LABELS:
        gap = abs(LABELS.index(model_label) - LABELS.index(label))
        agreement = gap == 0
        confidence -= 0.15 * gap
    return {
        "label": label,
        "score": round(score, 2),
        "base_score": round(base, 2),
        "measured_interaction": measured,
        "adjustments": [a.__dict__ for a in adjustments],
        "thresholds": thresholds,
        "confidence": round(max(0.2, min(0.95, confidence)), 2),
        "model_label": model_label,
        "model_agrees": agreement,
    }
