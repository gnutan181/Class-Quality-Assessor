"""Optional Zoom transcript (.vtt) support.

Zoom transcripts label every cue with the speaker's display name, which gives what
audio alone cannot: real per-speaker talk time, how many different children spoke,
and whether the tutor addressed children individually by name, which 8x8's own
reviewers check ("asked questions by calling individually", "consider everyone").

Names are replaced with "Teacher" / "Student N" before anything is sent to the LLM
or shown in the report.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path

from .signals import fmt_ts

_TS = re.compile(r"(\d{1,2}):(\d{2}):(\d{2})[.,](\d{3})\s*-->\s*(\d{1,2}):(\d{2}):(\d{2})[.,](\d{3})")
_SPEAKER = re.compile(r"^([^:]{1,60}?):\s+(.*)$")
_HOMEWORK = re.compile(r"\b(home ?works?|hw|assignments?|worksheet)\b", re.I)
_PRAISE = re.compile(r"\b(very good|good job|great|excellent|well done|super|awesome|"
                     r"correct|perfect|brilliant|nice|fantastic|amazing)\b", re.I)
_GREETING = re.compile(r"\b(hello|hi|good (morning|afternoon|evening)|welcome|how are you)\b", re.I)
_INTRO = re.compile(r"\b(introduce|introduction|your name|tell me about yourself|new (student|friend|joiner)s?)\b", re.I)
_RECAP = re.compile(r"\b(recap|summar|today we (learn|learnt|learned|saw|did)|what did we learn|"
                    r"see you|next class|bye)\b", re.I)


@dataclass
class Cue:
    start: float
    end: float
    speaker: str
    text: str


def _secs(h, m, s, ms) -> float:
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


def parse_vtt(text: str) -> list[Cue]:
    cues: list[Cue] = []
    block: list[str] = []
    for line in text.splitlines() + [""]:
        line = line.strip("﻿").rstrip()
        if line:
            block.append(line)
            continue
        if not block:
            continue
        ts_idx = next((i for i, l in enumerate(block) if _TS.search(l)), None)
        if ts_idx is not None:
            m = _TS.search(block[ts_idx])
            start, end = _secs(*m.groups()[:4]), _secs(*m.groups()[4:])
            body = " ".join(block[ts_idx + 1:]).strip()
            body = re.sub(r"</?v[^>]*>", "", body)
            sm = _SPEAKER.match(body)
            speaker, words = (sm.group(1).strip(), sm.group(2)) if sm else ("", body)
            if not speaker and cues:
                speaker = cues[-1].speaker  # continuation of the previous speaker
            if words:
                cues.append(Cue(start, max(end, start), speaker or "Unknown", words))
        block = []
    return cues


@dataclass
class TranscriptStats:
    speakers: int
    student_speakers: int
    teacher_talk_share: float          # share of spoken time by the tutor
    teacher_turns: int
    student_turns: int
    speaker_switches_per_min: float    # how conversational the class is
    students_with_3plus_turns: int     # breadth of participation
    students_addressed_by_name: int    # tutor said the child's name at least once
    name_mentions: int
    teacher_questions: int
    praise_count: int
    longest_teacher_monologue_s: float
    greeting_in_first_5min: bool
    intro_activity_in_first_15pct: bool
    homework_mentioned: bool
    homework_first_at: str | None
    recap_or_closure_in_last_15pct: bool

    def to_dict(self) -> dict:
        return asdict(self)


def _first_names(speaker: str) -> set[str]:
    tokens = [t for t in re.split(r"[\s._-]+", speaker) if len(t) >= 3 and t.isalpha()]
    return {t.lower() for t in tokens[:1]}


def analyse(cues: list[Cue]) -> tuple[TranscriptStats, dict[str, str]]:
    """Returns stats plus a pseudonym map {real speaker -> Teacher/Student N}."""
    if not cues:
        raise ValueError("empty transcript")
    talk: dict[str, float] = {}
    for c in cues:
        talk[c.speaker] = talk.get(c.speaker, 0.0) + (c.end - c.start)
    teacher = max(talk, key=talk.get)
    students = [s for s in sorted(talk, key=talk.get, reverse=True) if s != teacher]
    pseudo = {teacher: "Teacher", **{s: f"Student {i + 1}" for i, s in enumerate(students)}}

    t0, t1 = cues[0].start, cues[-1].end
    span = max(t1 - t0, 1.0)
    turns = {s: 0 for s in talk}
    switches, prev = 0, None
    for c in cues:
        if c.speaker != prev:
            turns[c.speaker] += 1
            if prev is not None:
                switches += 1
            prev = c.speaker

    teacher_cues = [c for c in cues if c.speaker == teacher]
    names = {s: _first_names(s) for s in students}
    addressed, mentions = set(), 0
    for c in teacher_cues:
        low = c.text.lower()
        for s, ns in names.items():
            if any(re.search(rf"\b{re.escape(n)}\b", low) for n in ns):
                addressed.add(s)
                mentions += 1

    longest, run_start, run_end = 0.0, None, None
    for c in cues:
        if c.speaker == teacher:
            if run_start is None:
                run_start = c.start
            run_end = c.end
        else:
            if run_start is not None:
                longest = max(longest, run_end - run_start)
            run_start = None
    if run_start is not None:
        longest = max(longest, run_end - run_start)

    hw = [c for c in teacher_cues if _HOMEWORK.search(c.text)]
    total_talk = sum(talk.values()) or 1.0
    stats = TranscriptStats(
        speakers=len(talk),
        student_speakers=len(students),
        teacher_talk_share=round(talk[teacher] / total_talk, 3),
        teacher_turns=turns[teacher],
        student_turns=sum(turns[s] for s in students),
        speaker_switches_per_min=round(switches / (span / 60), 2),
        students_with_3plus_turns=sum(1 for s in students if turns[s] >= 3),
        students_addressed_by_name=len(addressed),
        name_mentions=mentions,
        teacher_questions=sum(c.text.count("?") for c in teacher_cues),
        praise_count=sum(len(_PRAISE.findall(c.text)) for c in teacher_cues),
        longest_teacher_monologue_s=round(longest, 1),
        greeting_in_first_5min=any(_GREETING.search(c.text) for c in cues if c.start - t0 < 300),
        intro_activity_in_first_15pct=any(_INTRO.search(c.text) for c in cues
                                          if c.start - t0 < 0.15 * span),
        homework_mentioned=bool(hw),
        homework_first_at=fmt_ts(hw[0].start) if hw else None,
        recap_or_closure_in_last_15pct=any(_RECAP.search(c.text) for c in teacher_cues
                                           if c.start - t0 > 0.85 * span),
    )
    return stats, pseudo


def pseudonymised_text(cues: list[Cue], pseudo: dict[str, str], max_chars: int = 120_000) -> str:
    """'[mm:ss] Speaker: text' lines with names replaced, for the LLM prompt."""
    name_subs = []
    for real, alias in pseudo.items():
        tokens = {t.lower() for t in re.split(r"[\s._-]+", real) if len(t) >= 3 and t.isalpha()}
        for n in sorted(tokens | {real.lower()}, key=len, reverse=True):
            name_subs.append((re.compile(rf"\b{re.escape(n)}\b", re.I), alias))
    lines, prev = [], None
    for c in cues:
        text = c.text
        for rx, alias in name_subs:
            text = rx.sub(alias, text)
        who = pseudo.get(c.speaker, "Unknown")
        if who == prev and lines:
            lines[-1] += " " + text
        else:
            lines.append(f"[{fmt_ts(c.start)}] {who}: {text}")
        prev = who
    out = "\n".join(lines)
    if len(out) > max_chars:  # keep start and end, where intro and homework happen
        half = max_chars // 2
        out = out[:half] + "\n[... middle of transcript omitted for length ...]\n" + out[-half:]
    return out


def find_transcript(video: Path) -> Path | None:
    """Pair a recording with its Zoom .vtt in the same folder by batch code (e.g. B435)."""
    vtts = sorted(video.parent.glob("*.vtt"))
    code = video.name.split()[0].lower()
    hits = [p for p in vtts if p.name.lower().startswith(code)]
    if len(hits) > 1:  # same batch twice in one folder: match on the word after the code
        word = (video.name.split() + [""])[1].lower()
        hits = [p for p in hits if word in p.name.lower()] or hits
    return hits[0] if hits else None
