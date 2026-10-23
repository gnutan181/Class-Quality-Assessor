"""Developer tool: run measured signals + transcript stats over the labelled folders; print numbers only."""
import json, sys, glob, os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from assessor import media, signals, transcript
from assessor.transcript import find_transcript
root = Path(sys.argv[1]); out = []
for vid in sorted(root.glob("*/*.mp4")):
    label = vid.parent.name
    row = {"folder": label, "id": vid.name.split()[0] + "_" + vid.stem.split()[-1][-5:]}
    try:
        info = media.probe(vid)
        row["dur_min"] = round(info.duration_s / 60, 1)
        a = signals.analyse_audio(media.decode_audio(vid)).to_dict()
        a.pop("silence_spans"); row.update({"a_" + k: v for k, v in a.items() if k != "duration_s"})
        fr, _ = media.low_res_frames(vid)
        v = signals.analyse_visual(fr, round(info.duration_s / max(len(fr), 1), 2))
        if v: row.update({"v_" + k: x for k, x in v.to_dict().items() if k != "sampled_every_s"})
    except Exception as e:
        row["media_err"] = str(e)[:100]
    vtt = find_transcript(vid)
    if vid.parent.name == "demo":
        lang = "malayalam" if "malayalam" in vid.name.lower() else "english"
        vtt = next((p for p in vid.parent.glob("*.vtt") if lang in p.name.lower()), None)
    if vtt:
        st, _ = transcript.analyse(transcript.parse_vtt(vtt.read_text(errors="ignore")))
        row.update({"t_" + k: x for k, x in st.to_dict().items()})
    out.append(row); print(json.dumps(row), flush=True)
