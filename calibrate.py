"""Calibrate the label thresholds on the labelled sample recordings.

Run locally (recordings must not leave your machine except to the Gemini API):

    python calibrate.py --data ./recordings
    python calibrate.py --data ./recordings --labels labels.csv

Labels come from labels.csv (columns: file,label) or, if absent, from the file name
containing Poor/Average/Good/Excellent. Per-file reports are cached in
results/cache/ (git-ignored). The printed table contains only scores, so it is safe
to share. Writes calibration.json, which the app picks up automatically.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import statistics
import sys
import tempfile
from pathlib import Path

from assessor import pipeline
from assessor.transcript import find_transcript
from assessor.rubric import CALIBRATION_FILE, DEFAULT_THRESHOLDS, LABELS, label_for

MEDIA_EXT = {".mp4", ".mkv", ".webm", ".mov", ".avi", ".mp3", ".m4a", ".wav"}
# Folder names used in the 8x8 sample set -> rubric labels. "quality issue" classes are
# rated Poor overall in this scheme; "demo" classes are unlabelled and skipped.
ALIASES = {"excellent": "Excellent", "good": "Good", "average": "Average",
           "weak": "Poor", "poor": "Poor", "quality issue": "Poor", "quality issues": "Poor"}




def read_labels(data: Path, labels_csv: Path | None) -> dict[str, str]:
    out: dict[str, str] = {}
    if labels_csv:
        with open(labels_csv, newline="") as f:
            for row in csv.DictReader(f):
                out[row["file"].strip()] = row["label"].strip().title()
    for p in sorted(data.rglob("*")):
        if p.suffix.lower() in MEDIA_EXT and p.name not in out:
            folder = p.parent.name.lower()
            if folder in ALIASES:
                out[p.name] = ALIASES[folder]
                continue
            hit = [lab for lab in LABELS if lab.lower() in str(p.relative_to(data)).lower()]
            if len(hit) == 1:
                out[p.name] = hit[0]
    return out


def fit_thresholds(scores: dict[str, list[float]]) -> list[float]:
    """Cut points halfway between neighbouring class medians, defaults where a class
    is missing. Deliberately simple: with a handful of samples, anything fancier overfits."""
    med = {lab: statistics.median(v) for lab, v in scores.items() if v}
    cuts = []
    for i in range(3):
        lo, hi = LABELS[i], LABELS[i + 1]
        if lo in med and hi in med and med[lo] < med[hi]:
            cuts.append(round((med[lo] + med[hi]) / 2, 2))
        else:
            cuts.append(DEFAULT_THRESHOLDS[i])
    for i in range(1, 3):  # keep them strictly increasing
        if cuts[i] <= cuts[i - 1]:
            cuts[i] = round(cuts[i - 1] + 0.2, 2)
    return cuts


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--labels", type=Path)
    ap.add_argument("--no-write", action="store_true", help="don't write calibration.json")
    ap.add_argument("--no-transcripts", action="store_true", help="ignore .vtt files")
    ap.add_argument("--only", help="assess just files whose name contains this text")
    args = ap.parse_args()
    args.data = args.data.expanduser().resolve()  # follows Drive shortcuts / symlinks

    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        print("Set GEMINI_API_KEY first", file=sys.stderr)
        return 1
    labels = read_labels(args.data, args.labels)
    files = [p for p in sorted(args.data.rglob("*")) if p.name in labels]
    if args.only:
        files = [p for p in files if args.only.lower() in p.name.lower()]
    if not files:
        print("No labelled recordings found", file=sys.stderr)
        return 1

    cache = Path("results/cache")
    cache.mkdir(parents=True, exist_ok=True)
    rows = []
    for p in files:
        vtt = None if args.no_transcripts else find_transcript(p)
        cached = cache / f"{p.parent.name}__{p.stem}{'' if vtt else '__novtt'}.json"
        if cached.exists():
            report = json.loads(cached.read_text())
        else:
            print(f"Assessing {p.name} …", file=sys.stderr)
            with tempfile.TemporaryDirectory() as tmp:
                try:
                    report = pipeline.run(p, Path(tmp), api_key, vtt_path=vtt,
                                          log=lambda m: print("   ", m, file=sys.stderr))
                except Exception as e:  # noqa: BLE001
                    print(f"   failed: {e}", file=sys.stderr)
                    continue
            cached.write_text(json.dumps(report, indent=2))
        r, a = report["rating"], report["signals"]["audio"]
        v = report["signals"]["visual"] or {}
        rows.append({
            "file": p.name, "folder": p.parent.name, "true": labels[p.name], "score": r["score"],
            "base": r["base_score"], "model_label": r["model_label"],
            **{f"d_{k}": d["score"] for k, d in report["dimensions"].items()},
            "speech_ratio": a["speech_ratio"], "longest_silence_s": a["longest_silence_s"],
            "silences_10s": a["silences_over_10s"], "snr_db": a["snr_db"],
            "loud_var_db": a["loudness_variation_db"],
            "screen_chg_min": v.get("screen_changes_per_min"), "static": v.get("static_ratio"),
            "teacher_talk": report["talk"]["teacher_talk_pct"],
            "questions": report["talk"]["teacher_questions"],
            "answers": report["talk"]["student_responses"],
            **{f"t_{k}": val for k, val in (report["signals"].get("transcript") or {}).items()},
            **{f"setup_{k}": val for k, val in (report.get("setup") or {}).items() if k != "notes"},
        })

    by_label: dict[str, list[float]] = {lab: [] for lab in LABELS}
    for row in rows:
        by_label[row["true"]].append(row["score"])
    cuts = fit_thresholds(by_label)

    def acc(th):
        hits = sum(label_for(r["score"], th) == r["true"] for r in rows)
        off = sum(abs(LABELS.index(label_for(r["score"], th)) - LABELS.index(r["true"])) for r in rows)
        return hits, off

    for row in rows:
        row["pred_default"] = label_for(row["score"], DEFAULT_THRESHOLDS)
        row["pred_calibrated"] = label_for(row["score"], cuts)

    Path("results").mkdir(exist_ok=True)
    with open("results/calibration_table.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(dict.fromkeys(k for r in rows for k in r)))
        w.writeheader()
        w.writerows(rows)

    dim_keys = [k for k in rows[0] if k.startswith("d_")] if rows else []
    print("\nfolder,file,true,score,model_label,pred_default,pred_calibrated," + ",".join(dim_keys))
    for r in rows:
        print(f"{r['folder']},{r['file'][:12]},{r['true']},{r['score']},{r['model_label']},"
              f"{r['pred_default']},{r['pred_calibrated']}," + ",".join(str(r.get(k)) for k in dim_keys))
    h0, o0 = acc(DEFAULT_THRESHOLDS)
    h1, o1 = acc(cuts)
    print(f"\nDefault thresholds {DEFAULT_THRESHOLDS}: {h0}/{len(rows)} exact, total ordinal error {o0}")
    print(f"Calibrated thresholds {cuts}: {h1}/{len(rows)} exact, total ordinal error {o1}")
    print("Full numeric table: results/calibration_table.csv")
    if not args.no_write:
        CALIBRATION_FILE.write_text(json.dumps(
            {"thresholds": cuts, "n_samples": len(rows),
             "class_medians": {k: (statistics.median(v) if v else None) for k, v in by_label.items()}},
            indent=2))
        print(f"Wrote {CALIBRATION_FILE.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
