---
title: "AI Interaction History: Class Quality Assessor"
subtitle: "Humaniti AI 24-hour build challenge"
---

# Summary

| | |
|---|---|
| **Assistant** | Claude (Claude Code, Anthropic), with a cloud sandbox for code and tests and approved folder access to my local copy of the challenge files |
| **Model inside the app** | Google Gemini (audio + screenshots + transcript → structured rubric output) |
| **How I used AI** | I gave the brief and the constraints. I made the key decisions: the provider, keeping data local, and grounding the rubric in the reviewer feedback. The assistant designed and implemented the system, and I reviewed it and ran it |
| **Data handling** | No recording ever left my laptop or Google Drive for the coding assistant. Only aggregate numbers and the reviewer feedback were read |
| **Redactions** | My email, full name in file paths, a and all tutor and student names. No API keys were ever shared in chat |

My prompts are shown faithfully. Spelling and grammar are lightly corrected and marked
*(edited for spelling)*, with the meaning unchanged. The assistant's replies are condensed
and marked [...]. Routine progress updates are omitted.

# 1. Key decisions

| # | Decision | Who | Why |
|---|---|---|---|
| 1 | Don't upload the recordings to the coding assistant | Assistant proposed, I agreed | The brief requires confidentiality, and the recordings show children |
| 2 | Use Gemini as the runtime model | I chose it from three options | One free key, and it handles audio and images natively |
| 3 | Send audio plus 12 screenshots, not full video | Assistant | About 8x fewer tokens per hour of class, which fits free-tier limits |
| 4 | Final label computed in code from a weighted rubric, not chosen by the LLM | Assistant | Reproducible, explainable and calibratable |
| 5 | Rebuild the rubric from 8x8's own reviewer feedback | Assistant, after I pointed it to `feedbacks.pdf` | Matches what the company actually grades |
| 6 | Measure the samples locally (numbers only) before trusting any LLM | Assistant | Evidence first: it showed which signals separate quality levels |
| 7 | Process the 1.7 GB of recordings where they already are, never re-upload them | I raised the size problem, the assistant designed the solution | Faster, and keeps the data confidential |

# 2. Conversation

**Me:** This is my first-round interview assessment. Give me the instructions for
submitting it. It is very important to me, so be rigorous and complete the whole
assessment. *(edited for spelling; attached: the challenge PDF)*

**Claude:** I've read the brief and I'm building the whole thing now [...] I can't open
the Drive folder from my side. Please don't upload the videos to me: the brief says to
keep them confidential [...] I'll give you a small script that you run on your laptop.
It prints only numbers, no content [...] I'm building on Google Gemini, because it
understands audio and images directly [...]

**Claude (options):** Which AI provider should the app use? Gemini (free key, native
audio and images), OpenAI (Whisper + GPT, paid) or Claude (paid, plus a separate
transcription step). *Note: Gemini's free tier may use inputs to improve Google's
products, which matters for children's recordings.*

**Me:** *Chose Google Gemini.*

**Claude:** The app is built and packaged [...] a Streamlit app where you upload a
recording or paste a link. It measures the media directly [...] Gemini scores seven
teaching dimensions, each backed by mm:ss evidence [...] The label is calculated from
those scores, so it can be tuned on the sample classes [...] Testing so far: all unit
tests pass on synthetic videos, and the full pipeline runs with a stand-in for Gemini.
It has not yet run against real Gemini or real classes.

**Me:** The recordings zip is 1.7 GB and takes too long to upload. Please re-read the
PDF and suggest a solution. The zip contains multiple recordings. I've extracted them
to `C:\Users\<user>\Downloads\Humanity ai\class recordings`, which also contains a
reviewer feedback file. *(edited for spelling)*

**Claude:** I can see your folder now: 12 recordings in six folders (excellent, good,
average, weak, quality issue, demo), plus Zoom transcripts and feedbacks.pdf. You don't
need to upload the 1.7 GB zip anywhere [...] The feedback file changes things. It shows
the criteria 8x8 grades on: rapport and intro, asking every child individually,
energetic interaction, homework, the 8x8 background, the tutor's camera and lighting,
and AV issues. I'm rebuilding the rubric around exactly those points [...] Only numbers
come back to me, not video.

**Claude:** [...] I measured all 12 classes on your laptop. Excellent classes had at
most about 55 s of tutor monologue and 12-15 speaker switches a minute. Average and Weak
classes had 130-450 s monologues.

**Me:** I also need to submit the AI interaction history and a brief explanation of at
most 300 words. *(edited for spelling)*

**Me:** I get this error when running locally: `ffmpeg failed: Unrecognized option
'vsync'`. *(edited for spelling)*

**Claude:** Newer ffmpeg versions renamed `-vsync` to `-fps_mode`. The app now tries the
new option first and falls back to the old one [...] I've updated `media.py` in your
folder.

# 3. Engineering log

Reconstructed from the assistant's tool calls in the same session.

1. **Scoping.** It read the brief and checked data access. The Drive connector could see
   the folder but not its files, and the sandbox couldn't reach Drive. It chose not to
   have the videos uploaded.
2. **First build.** It wrote the media handling (ffmpeg probe, audio and frame extraction,
   Drive and URL download), the signal detectors (energy-based speech/silence,
   frame-difference screen activity), a Gemini prompt with a Pydantic structured-output
   schema, a weighted rubric with capped signal adjustments, the Streamlit UI with a
   password gate, a calibration script, a Dockerfile for Hugging Face Spaces, and unit
   tests.
3. **Testing without real data.** It generated synthetic videos with ffmpeg. One was a
   tone with a 25 s silent gap, and the detector found the gap at exactly 00:40-01:05.
   It also ran the full pipeline end to end against a mocked Gemini client.
4. **Feedback-driven rubric.** It reworked the seven dimensions to match the reviewers'
   language: individual attention 22%, rapport & intro 18%, energy 16%, teaching clarity
   16%, conclusion & homework 10%, tutor presence & 8x8 setup 10%, AV quality 8%.
5. **Transcript module.** It parses Zoom VTT files and computes talk share, speaker
   switches per minute, the longest tutor monologue, greeting/intro, homework and
   closing. All names are replaced with "Teacher" / "Student N". It checked that no
   name tokens remained in any of the 12 transcripts.
6. **Local measurement, numbers only.** It ran over all 12 recordings on my machine:

   | Folder | Longest tutor monologue (s) | Speaker switches / min |
   |---|---|---|
   | excellent | 43, 53 | 12.1, 14.9 |
   | good | 108, 30 | 2.7, 13.8 |
   | average | 131, 147 | 3.0, 6.2 |
   | weak | 155, 447 | 3.8, 10.0 |
   | quality issue | 101, 126 | 7.3, 4.8 |

   These two signals became a 20% "measured interaction" component. Audio SNR read
   about 90 dB on every file, because Zoom suppresses noise. That made it meaningless,
   so it was removed from scoring.
7. **Performance.** Screen analysis was switched to keyframe-only decoding, which is
   about 10x faster on hour-long classes.
8. **Compatibility fix.** It added `-fps_mode` with a `-vsync` fallback, so the app works
   on both older and newer ffmpeg.

# 4. What I would do next

- Run the full Gemini calibration on all ten labelled samples and fit the thresholds.
- Use speaker diarisation when no transcript is available.
- Use more screenshots, or a short video clip, to catch brief camera-off moments.
