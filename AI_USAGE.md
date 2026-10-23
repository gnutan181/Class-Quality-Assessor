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
   its measurement code on my laptop's copy and only numeric results came back.
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
8. **Hosting.** Claude added deployment files (`packages.txt` for ffmpeg, a Dockerfile)
   and a password gate so the public app does not expose recordings. I deployed it on
   Streamlit Community Cloud.
9. **Debugging.** Running locally I hit `ffmpeg failed: Unrecognized option 'vsync'`;
   Claude traced it to newer ffmpeg removing `-vsync` and added `-fps_mode` with a fallback.

## My own work

- Defined the task and constraints for the assistant, chose Gemini as the runtime model
  and agreed to process the recordings locally rather than upload them.
- Pointed the assistant to the 8x8 reviewer feedback, which became the basis of the rubric.
- Ran the app locally, reported the ffmpeg error, and verified the fix.
- Created the GitHub repository, deployed the app on Streamlit Community Cloud, and tested
  the hosted version.
- Not done in the time window: a full Gemini calibration run over all ten labelled
  samples (`calibrate.py`), so the label thresholds are still the defaults.
