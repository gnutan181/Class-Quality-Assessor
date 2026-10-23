from assessor.transcript import analyse, parse_vtt, pseudonymised_text

VTT = """WEBVTT

1
00:00:01.000 --> 00:00:04.000
Ms Teacher: Hello everyone, good evening! Riya, how are you?

2
00:00:05.000 --> 00:00:06.000
Riya K: I am fine ma'am.

3
00:00:07.000 --> 00:00:40.000
Ms Teacher: Today we learn fractions. What is half of eight?

4
00:00:41.000 --> 00:00:42.000
Arjun: Four!

5
00:00:43.000 --> 00:00:50.000
Ms Teacher: Very good Arjun. For homework do page 3. See you next class, bye!
"""


def test_parse_and_stats():
    cues = parse_vtt(VTT)
    assert len(cues) == 5 and cues[1].speaker == "Riya K"
    stats, pseudo = analyse(cues)
    assert pseudo["Ms Teacher"] == "Teacher"
    assert stats.student_speakers == 2
    assert stats.students_addressed_by_name == 2
    assert stats.homework_mentioned and stats.praise_count >= 1
    assert stats.greeting_in_first_5min and stats.recap_or_closure_in_last_15pct
    assert stats.longest_teacher_monologue_s == 33.0


def test_pseudonymised_text_hides_names():
    cues = parse_vtt(VTT)
    _, pseudo = analyse(cues)
    text = pseudonymised_text(cues, pseudo)
    assert "Riya" not in text and "Arjun" not in text and "Teacher:" in text
