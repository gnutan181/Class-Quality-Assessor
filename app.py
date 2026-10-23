"""Streamlit front end: upload a class recording (or paste a link) and get a rated,
evidence-backed quality assessment."""
from __future__ import annotations

import hmac
import json
import os
import tempfile
from pathlib import Path

import streamlit as st

from assessor import media, pipeline
from assessor.rubric import LABELS

st.set_page_config(page_title="Class Quality Assessor", page_icon="🎓", layout="wide")

LABEL_COLOURS = {"Poor": "#c0392b", "Average": "#d68910", "Good": "#2e86c1", "Excellent": "#1e8449"}


def secret(name: str, default: str = "") -> str:
    try:
        if name in st.secrets:
            return str(st.secrets[name])
    except Exception:  # noqa: BLE001 - no secrets file locally
        pass
    return os.environ.get(name, default)


def password_gate() -> bool:
    """Recordings are confidential, so the hosted app can be locked with APP_PASSWORD."""
    expected = secret("APP_PASSWORD")
    if not expected or st.session_state.get("authed"):
        return True
    st.title("🎓 Class Quality Assessor")
    pw = st.text_input("Access password", type="password")
    if pw:
        if hmac.compare_digest(pw, expected):
            st.session_state["authed"] = True
            st.rerun()
        st.error("Wrong password")
    return False


def render(report: dict) -> None:
    r = report["rating"]
    colour = LABEL_COLOURS.get(r["label"], "#555")
    c1, c2, c3 = st.columns([2, 1, 1])
    c1.markdown(
        f"<div style='padding:18px;border-radius:12px;background:{colour};color:white'>"
        f"<div style='font-size:14px;opacity:.85'>Overall quality</div>"
        f"<div style='font-size:40px;font-weight:700'>{r['label']}</div>"
        f"<div style='font-size:14px'>Score {r['score']} / 4</div></div>",
        unsafe_allow_html=True)
    c2.metric("Confidence", f"{r['confidence']:.0%}")
    c3.metric("Length", report["media"]["duration"])
    if r.get("model_agrees") is False:
        st.caption(f"Note: the model's holistic impression was **{r['model_label']}**; the label "
                   "above comes from the weighted rubric, so it sits near a boundary.")

    ctx = report["context"]
    st.markdown(f"**Class:** {ctx['subject']} · ages {ctx['approx_student_age']} · "
                f"{ctx['format']} · {ctx['language']}")
    st.write(report["summary"])

    left, right = st.columns(2)
    with left:
        st.subheader("✅ What worked")
        for s in report["strengths"]:
            st.markdown(f"- {s}")
    with right:
        st.subheader("🛠️ What to improve")
        for s in report["improvements"]:
            st.markdown(f"- {s}")

    st.subheader("Rubric breakdown")
    rows = [{"Dimension": d["name"], "Weight": f"{d['weight']:.0%}", "Score (1-4)": d["score"]}
            for d in report["dimensions"].values()]
    st.dataframe(rows, hide_index=True, use_container_width=True)
    for d in report["dimensions"].values():
        with st.expander(f"{d['name']}: {d['score']}/4"):
            st.write(d["rationale"])
            for e in d["evidence"]:
                icon = "🟢" if e["impact"] == "positive" else "🔴"
                quote = f' *"{e["quote"]}"*' if e.get("quote") else ""
                st.markdown(f"{icon} **{e['timestamp']}** {e['observation']}{quote}")

    st.subheader("Measured signals")
    a = report["signals"]["audio"]
    v = report["signals"]["visual"]
    t = report["talk"]
    m = st.columns(4)
    m[0].metric("Speech in recording", f"{a['speech_ratio']:.0%}")
    m[1].metric("Longest silence", f"{a['longest_silence_s']:.0f}s")
    m[2].metric("Teacher / student talk", f"{t['teacher_talk_pct']}% / {t['student_talk_pct']}%")
    m[3].metric("Teacher questions → answers", f"{t['teacher_questions']} → {t['student_responses']}")
    if v:
        m = st.columns(4)
        m[0].metric("Screen changes / min", v["screen_changes_per_min"])
        m[1].metric("Static screen", f"{v['static_ratio']:.0%}")
        m[2].metric("Blank video", f"{v['black_ratio']:.0%}")
        m[3].metric("Silences > 10 s", a["silences_over_10s"])
    tr = report["signals"].get("transcript")
    if tr:
        st.markdown("**From the Zoom transcript**")
        m = st.columns(4)
        m[0].metric("Children who spoke", tr["student_speakers"])
        m[1].metric("Children with 3+ turns", tr["students_with_3plus_turns"])
        m[2].metric("Tutor talk time", f"{tr['teacher_talk_share']:.0%}")
        m[3].metric("Speaker switches / min", tr["speaker_switches_per_min"])
        m = st.columns(4)
        m[0].metric("Children addressed by name", tr["students_addressed_by_name"])
        m[1].metric("Praise phrases", tr["praise_count"])
        m[2].metric("Homework", tr["homework_first_at"] or "not mentioned")
        m[3].metric("Closing / recap", "yes" if tr["recap_or_closure_in_last_15pct"] else "no")
    su = report.get("setup")
    if su:
        n = report["media"]["screenshots_used"] or 1
        st.markdown(f"**Tutor setup (from {n} screenshots):** 8x8 background in "
                    f"{su['screenshots_with_8x8_background']}, face visible in "
                    f"{su['screenshots_with_tutor_face_visible']}, camera off in "
                    f"{su['screenshots_with_tutor_camera_off']}; lighting {su['lighting']}. "
                    f"{su['notes']}")
    if r["adjustments"]:
        st.markdown("**Score adjustments from measurements:** " + "; ".join(
            f"{x['reason']} ({x['delta']:+.2f})" for x in r["adjustments"]))
    if report["misleading_signals"]:
        st.markdown("**Signals the model treated with caution:**")
        for s in report["misleading_signals"]:
            st.markdown(f"- {s}")
    st.caption(f"Base rubric score {r['base_score']} · model {report['model']} · "
               f"{report['media']['screenshots_used']} screenshots analysed")
    st.download_button("Download full report (JSON)", json.dumps(report, indent=2),
                       file_name="class_assessment.json", mime="application/json")


def main() -> None:
    if not password_gate():
        return
    st.title("🎓 Class Quality Assessor")
    st.write("Upload an online class recording, or paste a link, and get a rating of "
             f"**{' / '.join(LABELS)}** with timestamped evidence for it.")

    api_key = secret("GEMINI_API_KEY") or secret("GOOGLE_API_KEY")
    if not api_key:
        api_key = st.sidebar.text_input("Gemini API key", type="password",
                                        help="Not stored. Set GEMINI_API_KEY to skip this.")
    models = [m.strip() for m in secret("GEMINI_MODEL").split(",") if m.strip()] or None

    with st.sidebar:
        st.header("How it works")
        st.markdown(
            "1. Measures the raw media: speech vs silence, long pauses, loudness and noise, "
            "screen activity.\n"
            "2. Optional Zoom transcript: exact talk time per speaker, how many children "
            "spoke, names, homework, closing (names are pseudonymised).\n"
            "3. Gemini listens to the full audio, looks at 12 timestamped screenshots "
            "(8x8 background, tutor camera) and scores 7 dimensions taken from 8x8's own "
            "reviewer feedback, with evidence.\n"
            "4. The label comes from the weighted rubric (calibrated on the sample classes), "
            "with small, visible adjustments from the measurements.")
        st.header("Privacy")
        st.markdown("Recordings are processed in a temporary folder and deleted straight "
                    "after. The audio uploaded to Gemini is deleted when the analysis ends. "
                    "Nothing is stored or logged.")

    tab_up, tab_link = st.tabs(["Upload a recording", "Paste a link"])
    with tab_up:
        uploaded = st.file_uploader("Recording (mp4, mkv, webm, mov, mp3, m4a, wav)",
                                    type=["mp4", "mkv", "webm", "mov", "avi", "mp3", "m4a", "wav"])
    with tab_link:
        link = st.text_input("Google Drive file link (shared as 'anyone with the link') "
                             "or a direct link to a media file")
    vtt = st.file_uploader("Optional: the Zoom transcript (.vtt) for this class. It gives exact "
                           "talk time per speaker and how many children spoke.", type=["vtt"])

    if not st.button("Assess class", type="primary", disabled=not (uploaded or link)):
        return
    if not api_key:
        st.error("A Gemini API key is needed")
        return

    with tempfile.TemporaryDirectory(prefix="class_") as tmp:
        work = Path(tmp)
        try:
            with st.status("Assessing the class…", expanded=True) as status:
                if uploaded:
                    status.write("Saving upload")
                    path = media.save_upload(uploaded, work)
                else:
                    status.write("Downloading from link")
                    path = media.fetch_link(link, work)
                vtt_path = None
                if vtt is not None:
                    vtt_path = work / "transcript.vtt"
                    vtt_path.write_bytes(vtt.getvalue())
                report = pipeline.run(path, work, api_key, models=models,
                                      vtt_path=vtt_path, log=status.write)
                status.update(label="Done", state="complete", expanded=False)
        except media.MediaError as e:
            st.error(str(e))
            return
        except Exception as e:  # noqa: BLE001
            st.error(f"Assessment failed: {e}")
            return
    st.session_state["report"] = report


if __name__ == "__main__":
    main()
    if "report" in st.session_state:
        render(st.session_state["report"])
