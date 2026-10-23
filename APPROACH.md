# Approach (≤300 words)

**Start from the reviewers, not from generic pedagogy.** 8x8's feedback on the sample
classes repeatedly mentions rapport and intro, asking every child individually, energetic
and pleasant interaction, homework, the 8x8 background, the tutor's camera and face, and
known AV problems. I turned exactly those points into a seven-dimension weighted rubric.

**Three evidence sources.** (1) Measurements from the raw media: speech vs silence, long
pauses and screen activity. (2) The Zoom transcript, when available: per-speaker talk
time, speaker switches and the longest tutor monologue. Names are pseudonymised before
the transcript goes anywhere. (3) Gemini, which listens to the full audio, reads the
transcript and checks 12 screenshots for the background, the camera and the lighting.
For each dimension it returns 1-4 with timestamped quotes.

**What worked.** Before using any LLM, I measured all 10 labelled classes. Two transcript
signals tracked quality best. Excellent classes had a longest tutor monologue of about
45-55 s and 12-15 speaker switches per minute. Average and Weak classes had 130-450 s
monologues and mostly 3-6 switches. These signals make up 20% of the score. The final
label is calculated in code from the rubric, so it can be reproduced and is calibrated on
the samples. [Add the calibration result: X/10 exact, Y within one level.]

**Misleading signals.** Audio "SNR" looked perfect because Zoom suppresses noise, so I
dropped it. Silence often means children are solving a puzzle. Name-matching undercounts
individual attention when a child's Zoom name is a parent's name.

**Limitations.** There are only 10 labelled examples, and "quality issue" classes are
treated as Poor. Without a transcript, speaker balance is the model's estimate. Twelve
screenshots can miss brief camera-off moments. Child privacy needs a billing-enabled
Gemini key, which Google does not train on.
