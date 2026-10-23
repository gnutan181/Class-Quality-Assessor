# AI usage

AI assistance was used throughout, as the challenge encourages. The full conversation
export is submitted separately; this is a summary of how each assistant was used.

## Claude (Claude Code), research, design and implementation

Main prompts and decisions, in order:

1. *"This is my interview first round… complete the assessment"*, with the challenge PDF.
   Claude read the brief and proposed the architecture: measured signals + LLM rubric
   + deterministic, calibratable scoring.
2. **Provider choice.** Claude compared Gemini, OpenAI and Claude. Gemini was chosen
   because it accepts audio and images natively with one free key.
3. **Data handling.** Claude flagged that the recordings are confidential and involve
   children, so the videos were never uploaded to the coding assistant. Instead it ran
   its measurement code on my laptop's copy and only numeric results came back. The
   Gemini calibration runs in Colab, which reads the recordings directly from Google Drive.
4. **Using the reviewer feedback.** After reading `feedbacks.pdf`, Claude rebuilt the
   rubric around 8x8's actual criteria: rapport, individual attention, energy, homework,
   8x8 background and camera, and AV quality. It also added Zoom transcript support
   (with pseudonymised names), because transcripts show who spoke and when.
5. **Evidence first.** `tools/measure_all.py` measured all 12 samples without any LLM.
   This showed that the longest tutor monologue and the speaker switches per minute
   separate the quality levels, and that audio SNR is meaningless on Zoom recordings.
   The rubric weights were set from that.
6. **Token budget.** Claude suggested sending compressed audio plus 12 screenshots
   instead of full video (about 120k vs 1M tokens per hour of class).
7. **Implementation.** Claude wrote the modules, the Gemini structured-output schema and
   prompt, and the Streamlit UI, and tested the media/signal code on synthetic videos
   generated with ffmpeg (tones with silent gaps, changing test patterns). It also
   tested the full pipeline end to end with a mocked Gemini client.
8. **Hosting.** Claude added a Dockerfile for Hugging Face Spaces (16 GB RAM handles long
   uploads) and a password gate so the public app does not expose recordings.

## My own work

- Downloaded the samples, ran `calibrate.py` locally, reviewed the per-class results and
  checked the evidence the app quoted against the actual recordings.
- [Add: anything you changed after reviewing results, e.g. weight or prompt tweaks.]

## Gemini, inside the product

Gemini (`gemini-2.5-flash`) is the runtime model that assesses each class. Its system
prompt is in `assessor/llm.py`.
