# Class Quality Assessor

**Live app:** https://2ckkowxhcs9hknnkzvhnm9.streamlit.app/


Upload a recording of an online children's class (or paste a link) and get a rating of
**Poor / Average / Good / Excellent**, with timestamped, specific evidence for each
part of the judgement and concrete coaching points.

Built for the Humaniti AI 24-hour build challenge. See [APPROACH.md](APPROACH.md) for
the reasoning behind the design and [AI_USAGE.md](AI_USAGE.md) for how AI was used, and
[docs/AI_INTERACTION_HISTORY.pdf](docs/AI_INTERACTION_HISTORY.pdf) for the AI interaction history.

## How it works

```
recording (+ optional Zoom .vtt transcript)
   │
   ├─► measured signals (ffmpeg + numpy, no model)
   │     speech vs silence, long pauses with timestamps, screen activity
   ├─► transcript stats (if .vtt given; names → "Teacher"/"Student N")
   │     per-speaker talk time, speaker switches/min, longest tutor monologue,
   │     children who spoke, greeting/intro, homework, closing
   ├─► compressed mono audio (~15 MB/hour) + 12 timestamped screenshots
   ▼
Gemini: listens to the whole class, reads the pseudonymised transcript, checks the
screenshots (8x8 background, tutor face/camera, lighting) and scores 7 rubric
dimensions 1-4, each with mm:ss evidence and quotes
   ▼
score = 80% weighted rubric + 20% measured interaction (transcript), ± small capped
signal adjustments ──► thresholds calibrated on the labelled samples ──► label + confidence
```

The rubric comes from 8x8's own reviewer feedback on the sample classes:

| Rubric dimension | Weight | What reviewers said |
|---|---|---|
| Individual attention & participation | 22% | "asked questions by calling individually", "consider everyone in the class" |
| Rapport building & introduction | 18% | "good rapport building", "directly entered into class without proper rapport building", "time for new joiners to self-introduce" |
| Energy & pleasant interaction | 16% | "need more energetic and pleasant interaction" |
| Teaching clarity & activities | 16% | "clarity issues", puzzles, "topic related videos" |
| Conclusion & homework | 10% | "given HWs", "need a better intro and conclusion" |
| Tutor presence & 8x8 setup | 10% | "fixed 8x8 background", "can't see his face", "camera was turned off", "sit where there is light" |
| Audio/video quality | 8% | "known quality issues" |

**What the measurements showed.** Before any LLM call, `tools/measure_all.py` measured all
labelled samples. The two transcript signals that best tracked quality were the
longest uninterrupted tutor monologue (Excellent ≈45-55 s; Average/Weak 130-450 s) and
speaker switches per minute (Excellent 12-15; Average/Weak mostly 3-6). They form the
20% "measured interaction" part of the score. Audio SNR turned out to be meaningless
(Zoom's noise suppression makes every recording look clean), so it is shown but not scored.

The label is computed in code, not chosen freely by the model, so it is reproducible and
tunable. The model's own holistic label is kept as a cross-check: when the two disagree,
confidence drops and the UI says so.

## Run locally

Needs Python 3.10+ and `ffmpeg` on the PATH.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # add GEMINI_API_KEY
streamlit run app.py
```

Get a free key at <https://aistudio.google.com/apikey>.

On Windows, after dependencies and FFmpeg are installed, start the app with
`powershell -ExecutionPolicy Bypass -File .\start.ps1`. Open <http://localhost:8501> and
enter your Gemini API key in the sidebar. The launcher uses `.venv` and also detects a
local FFmpeg in `.runtime\win32`.

### Deployment

The live app runs on Streamlit Community Cloud from this repository: `packages.txt`
installs ffmpeg, `requirements.txt` the Python packages, and `GEMINI_API_KEY` (plus the
optional `APP_PASSWORD`) are set in the app's **Secrets**. Long recordings are best given
as a Google Drive link rather than uploaded, because the free tier has limited memory.

Alternatively, with Docker (for example on Hugging Face Spaces):

```bash
docker build -t class-assessor .
docker run -p 7860:7860 -e GEMINI_API_KEY=... class-assessor
```

### Configuration (environment variables or Streamlit secrets)

| Name | Required | Purpose |
|---|---|---|
| `GEMINI_API_KEY` | yes | Gemini API key |
| `APP_PASSWORD` | no | Locks the hosted app (recordings are confidential) |
| `GEMINI_MODEL` | no | Comma-separated model fallback list, default `gemini-2.5-flash,gemini-flash-latest` |

## Calibrating on labelled recordings

```bash
export GEMINI_API_KEY=...
python calibrate.py --data "./class recordings"     # labels from folder names (excellent/good/average/weak/quality issue)
python calibrate.py --data ./recordings --labels labels.csv   # or file,label CSV
```

`colab_calibrate.ipynb` runs the same calibration on Google Colab, reading the
recordings directly from Google Drive.

Each video is paired with its Zoom `.vtt` in the same folder by batch code (e.g. `B435`).
`--only B472` runs a single file; results are cached in `results/cache/`.

This assesses every labelled recording, prints predicted vs true labels, fits the three
score thresholds to the class medians and writes `calibration.json`, which the app loads.
Recordings and per-file reports stay in git-ignored folders.

## Tests

```bash
pip install pytest && pytest -q
```

Unit tests cover the rubric maths and the audio/screen signal detectors on synthetic media.

## Privacy

- Recordings are never committed (see `.gitignore`) and are processed in a temporary
  directory that is deleted after each assessment.
- Only compressed audio and 12 small screenshots are sent to Gemini, and the uploaded
  audio is deleted from Gemini's file store as soon as the analysis ends.
- Zoom transcripts are pseudonymised (every speaker name → "Teacher" / "Student N")
  before they are sent to the model or shown; the prompt also forbids naming children.
- Use a billing-enabled Gemini key for real data: the free tier may use inputs to
  improve Google's products.

## Project layout

```
app.py                 Streamlit UI
assessor/media.py      download, probe, audio/frame extraction (ffmpeg)
assessor/signals.py    measured audio + screen signals
assessor/llm.py        Gemini prompt, structured output schema
assessor/rubric.py     rubric, weights, scoring, thresholds
assessor/transcript.py Zoom .vtt parsing, talk statistics, pseudonymisation
assessor/pipeline.py   end-to-end orchestration
calibrate.py           fit thresholds on the labelled samples
colab_calibrate.ipynb  run the calibration on Google Colab, reading recordings from Drive
tools/measure_all.py   model-free signal measurements over the sample folders
tests/                 unit tests
```
