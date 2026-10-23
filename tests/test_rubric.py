from assessor.rubric import DEFAULT_THRESHOLDS, LABELS, final_rating, label_for, weighted_score

ALL = ["individual_attention", "rapport_intro", "energy_warmth", "teaching_clarity", "closure_homework", "presence_setup", "av_quality"]


def test_labels_cover_range():
    assert label_for(1.0, DEFAULT_THRESHOLDS) == "Poor"
    assert label_for(2.2, DEFAULT_THRESHOLDS) == "Average"
    assert label_for(3.0, DEFAULT_THRESHOLDS) == "Good"
    assert label_for(4.0, DEFAULT_THRESHOLDS) == "Excellent"


def test_weighted_score_bounds():
    assert weighted_score({k: 4 for k in ALL}) == 4
    assert weighted_score({k: 1 for k in ALL}) == 1


def test_missing_dimensions_are_renormalised():
    assert abs(weighted_score({"individual_attention": 3, "rapport_intro": 3}) - 3) < 1e-9


def test_signal_penalties_capped():
    audio = {"speech_ratio": 0.2, "silences_over_10s": 20, "snr_db": 3, "clipping_ratio": 0.1}
    r = final_rating({k: 3 for k in ALL}, "Good", audio, {"black_ratio": 0.9})
    assert abs(r["base_score"] - 3) < 1e-9
    assert r["score"] >= 2.7 - 1e-9
    assert r["label"] in LABELS


def test_disagreement_lowers_confidence():
    a = final_rating({k: 3 for k in ALL}, "Good", None, None)
    b = final_rating({k: 3 for k in ALL}, "Poor", None, None)
    assert b["confidence"] < a["confidence"] and b["model_agrees"] is False


def test_transcript_interaction_blend():
    talk_good = {"longest_teacher_monologue_s": 45, "speaker_switches_per_min": 13, "homework_mentioned": True}
    talk_bad = {"longest_teacher_monologue_s": 400, "speaker_switches_per_min": 3, "homework_mentioned": False}
    hi = final_rating({k: 3 for k in ALL}, "Good", None, None, talk=talk_good)
    lo = final_rating({k: 3 for k in ALL}, "Good", None, None, talk=talk_bad)
    assert hi["measured_interaction"] == 4 and lo["measured_interaction"] == 1
    assert hi["score"] > 3 > lo["score"]
