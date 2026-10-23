"""Gemini-based assessment of the class.

The model receives the class *audio* (so it hears tone, pace, who speaks and when),
a handful of timestamped screenshots (what happens on screen) and the measured
signals, and must return structured, evidence-backed rubric scores.

Sending audio + frames instead of the full video keeps a 1-hour class at roughly
120k tokens instead of ~1M, which is faster, cheaper and fits free-tier limits.
"""
from __future__ import annotations

import json
import time
from enum import Enum
from pathlib import Path

from pydantic import BaseModel

from .rubric import DIMENSIONS
from .signals import fmt_ts

DEFAULT_MODELS = ["gemini-2.5-flash", "gemini-flash-latest"]


class Label(str, Enum):
    Poor = "Poor"
    Average = "Average"
    Good = "Good"
    Excellent = "Excellent"


class Impact(str, Enum):
    positive = "positive"
    negative = "negative"


DimensionKey = Enum("DimensionKey", {k: k for k in DIMENSIONS}, type=str)


class Evidence(BaseModel):
    timestamp: str          # mm:ss in the recording
    observation: str        # what happened, concretely
    quote: str              # short verbatim quote if spoken, else ""
    impact: Impact


class DimensionScore(BaseModel):
    dimension: DimensionKey
    score: int              # 1-4
    rationale: str
    evidence: list[Evidence]


class ClassContext(BaseModel):
    subject: str
    approx_student_age: str
    language: str
    format: str             # e.g. "1:1", "small group", "lecture"
    is_a_class: bool        # false if the input is not a teaching session


class TalkBalance(BaseModel):
    teacher_talk_pct: int
    student_talk_pct: int
    teacher_questions: int
    student_responses: int


class SetupChecks(BaseModel):
    screenshots_with_8x8_background: int    # out of the screenshots provided
    screenshots_with_tutor_face_visible: int
    screenshots_with_tutor_camera_off: int
    lighting: str                           # "good", "dim" or "poor"
    notes: str


class ModelAssessment(BaseModel):
    context: ClassContext
    setup: SetupChecks
    summary: str
    talk: TalkBalance
    dimensions: list[DimensionScore]
    strengths: list[str]
    improvements: list[str]
    misleading_signals: list[str]
    overall_label: Label


def _rubric_text() -> str:
    lines = []
    for key, (name, weight, guide) in DIMENSIONS.items():
        lines.append(f"- {key} ({name}, weight {weight:.0%}): {guide}")
    return "\n".join(lines)


SYSTEM = f"""You are an experienced teaching-quality reviewer for 8x8, an online education
company that runs small-group live classes for children on Zoom. You review one class
recording and judge it the way 8x8's own reviewers do. Their feedback on real classes
praises "good rapport building", "consider everyone in the class", "asked questions by
calling individually", "given HWs" and "fixed 8x8 background". It criticises "directly
entered into class without proper rapport building", "need more energetic and pleasant
interaction", "should give time for new joiners for self-introduction", "tutor's camera
was turned off", "can't see his face", "no background" and repeated quality issues.

Score every rubric dimension from 1 to 4:
1 = poor (clearly hurts learning), 2 = average (works but with real weaknesses),
3 = good (effective, minor issues), 4 = excellent (model practice worth copying).

Rubric:
{_rubric_text()}

Rules:
- Ground every claim in the recording. Each dimension needs 2-4 evidence items with an
  mm:ss timestamp; include a short verbatim quote when the evidence is speech.
- Be specific ("At 07:42 the teacher asks 'why do you think the ice melted?' and waits
  for a student to answer"), never generic ("the teacher is engaging").
- Use both positive and negative evidence where it exists. Do not inflate scores.
- Screenshots: count how many show the 8x8 branded virtual background, the tutor's face
  clearly, or the tutor's camera off, and judge lighting. Use this for presence_setup.
- A pseudonymised Zoom transcript may be provided ("Teacher", "Student 1"...). Prefer it
  for quotes and timestamps, and use its statistics for individual_attention. Check the
  start for rapport/intro and the end for conclusion and homework.
- Measured signals are provided. Use them, but think about whether they mislead: silence
  may be students solving a task, a static screen may be a deliberate worksheet, high
  teacher talk can be fine in a short demo, Zoom noise suppression makes "silence" look
  perfectly clean. Note such cases in misleading_signals.
- If audio is unclear or something cannot be judged, say so and score conservatively.
- If the input is not a teaching session, set is_a_class=false and score everything 1.
- Privacy: never name or describe individual children; say "a student" instead.
- improvements must be concrete, actionable coaching points for the teacher.
"""


def _client(api_key: str):
    from google import genai
    return genai.Client(api_key=api_key)


def _wait_active(client, f, timeout_s: int = 300):
    start = time.time()
    while getattr(f.state, "name", str(f.state)) == "PROCESSING":
        if time.time() - start > timeout_s:
            raise TimeoutError("Gemini took too long to process the audio")
        time.sleep(2)
        f = client.files.get(name=f.name)
    if getattr(f.state, "name", str(f.state)) == "FAILED":
        raise RuntimeError("Gemini could not process the audio file")
    return f


def assess(api_key: str, audio_path: Path, frames: list[tuple[float, Path]],
           signals: dict, duration_s: float, models: list[str] | None = None,
           transcript_text: str | None = None,
           log=lambda msg: None) -> tuple[ModelAssessment, str]:
    from google.genai import types

    client = _client(api_key)
    log("Uploading compressed audio to Gemini")
    uploaded = client.files.upload(file=str(audio_path), config={"mime_type": "audio/mpeg"})
    try:
        uploaded = _wait_active(client, uploaded)
        parts: list = [
            f"Class recording, total length {fmt_ts(duration_s)}. The audio track is attached.",
            uploaded,
        ]
        if frames:
            parts.append("Screenshots of the class, in order, each labelled with its timestamp:")
            for t, p in frames:
                parts.append(f"Screenshot at {fmt_ts(t)}:")
                parts.append(types.Part.from_bytes(data=p.read_bytes(), mime_type="image/jpeg"))
        else:
            parts.append("No video track was available; judge from audio only.")
        if transcript_text:
            parts.append("Pseudonymised Zoom transcript of the class:\n" + transcript_text)
        parts.append("Measured signals (computed from the raw media):\n"
                     + json.dumps(signals, indent=2))
        parts.append("Now assess this class according to the rubric and return JSON.")

        config = types.GenerateContentConfig(
            system_instruction=SYSTEM,
            temperature=0.2,
            response_mime_type="application/json",
            response_schema=ModelAssessment,
        )
        last_err: Exception | None = None
        for model in models or DEFAULT_MODELS:
            for attempt in range(3):
                try:
                    log(f"Asking {model} to assess the class")
                    resp = client.models.generate_content(model=model, contents=parts, config=config)
                    result = resp.parsed
                    if result is None:
                        result = ModelAssessment.model_validate_json(resp.text)
                    return result, model
                except Exception as e:  # noqa: BLE001 - surface the last provider error
                    last_err = e
                    msg = str(e)
                    if "404" in msg or "not found" in msg.lower():
                        break  # model unavailable, try the next one
                    if "429" in msg or "503" in msg or "overloaded" in msg.lower():
                        time.sleep(5 * (attempt + 1))
                        continue
                    if attempt == 2:
                        break
        raise RuntimeError(f"Gemini assessment failed: {last_err}")
    finally:
        try:
            client.files.delete(name=uploaded.name)  # don't leave the recording on Google's side
        except Exception:  # noqa: BLE001
            pass
