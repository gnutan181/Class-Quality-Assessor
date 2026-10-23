"""End-to-end assessment: media -> measured signals -> Gemini rubric -> final rating."""
from __future__ import annotations

from pathlib import Path

from . import media, signals, transcript
from .llm import assess as llm_assess
from .rubric import DIMENSIONS, final_rating

MIN_DURATION_S = 60


def measure(path: Path, log=lambda msg: None) -> tuple[media.MediaInfo, dict]:
    info = media.probe(path)
    if not info.has_audio:
        raise media.MediaError("The recording has no audio track, so it cannot be assessed")
    if info.duration_s < MIN_DURATION_S:
        raise media.MediaError("The recording is shorter than a minute, too short to judge a class")
    log("Measuring audio: speech, silences, loudness, noise")
    audio = signals.analyse_audio(media.decode_audio(path))
    visual = None
    if info.has_video:
        log("Measuring screen activity")
        frames, _ = media.low_res_frames(path)
        every = info.duration_s / max(len(frames), 1)
        visual = signals.analyse_visual(frames, round(every, 2))
    return info, {"audio": audio.to_dict(), "visual": visual.to_dict() if visual else None}


def load_transcript(vtt_path: Path | None):
    """Parse a Zoom .vtt if given. Returns (stats dict, pseudonymised text) or (None, None)."""
    if not vtt_path:
        return None, None
    cues = transcript.parse_vtt(Path(vtt_path).read_text(encoding="utf-8", errors="ignore"))
    if len(cues) < 5:
        return None, None
    stats, pseudo = transcript.analyse(cues)
    return stats.to_dict(), transcript.pseudonymised_text(cues, pseudo)


def run(path: Path, work_dir: Path, api_key: str, models: list[str] | None = None,
        n_frames: int = 12, vtt_path: Path | None = None, log=lambda msg: None) -> dict:
    info, measured = measure(path, log)
    talk_stats, transcript_text = load_transcript(vtt_path)
    if talk_stats:
        log(f"Transcript: {talk_stats['student_speakers']} children spoke, tutor talk "
            f"{talk_stats['teacher_talk_share']:.0%}")
        measured["transcript"] = talk_stats
    log("Preparing audio and screenshots")
    audio_mp3 = media.compress_audio(path, work_dir)
    frames = media.sample_frames(path, info, work_dir, n=n_frames)

    model_out, model_name = llm_assess(api_key, audio_mp3, frames, measured,
                                       info.duration_s, models=models,
                                       transcript_text=transcript_text, log=log)

    dims = {}
    for d in model_out.dimensions:
        key = d.dimension.value if hasattr(d.dimension, "value") else str(d.dimension)
        dims[key] = {
            "name": DIMENSIONS[key][0] if key in DIMENSIONS else key,
            "weight": DIMENSIONS[key][1] if key in DIMENSIONS else 0,
            "score": max(1, min(4, int(d.score))),
            "rationale": d.rationale,
            "evidence": [e.model_dump(mode="json") for e in d.evidence],
        }
    if not model_out.context.is_a_class:
        rating = {"label": "Poor", "score": 1.0, "base_score": 1.0, "adjustments": [
            {"reason": "The recording does not appear to be a teaching session", "delta": 0}],
            "thresholds": [], "confidence": 0.6, "model_label": model_out.overall_label.value,
            "model_agrees": None}
    else:
        rating = final_rating({k: v["score"] for k, v in dims.items()},
                              model_out.overall_label.value,
                              measured["audio"], measured["visual"], talk=talk_stats)
    missing = [k for k in DIMENSIONS if k not in dims]
    return {
        "rating": rating,
        "dimensions": dims,
        "missing_dimensions": missing,
        "context": model_out.context.model_dump(mode="json"),
        "summary": model_out.summary,
        "talk": model_out.talk.model_dump(mode="json"),
        "setup": model_out.setup.model_dump(mode="json"),
        "transcript_used": bool(talk_stats),
        "strengths": model_out.strengths,
        "improvements": model_out.improvements,
        "misleading_signals": model_out.misleading_signals,
        "signals": measured,
        "media": {"duration": signals.fmt_ts(info.duration_s), "has_video": info.has_video,
                  "resolution": f"{info.width}x{info.height}" if info.has_video else None,
                  "screenshots_used": len(frames)},
        "model": model_name,
    }
