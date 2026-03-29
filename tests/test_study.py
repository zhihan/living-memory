from __future__ import annotations
from datetime import date, datetime, timezone, timedelta
import pytest
from study import StreakResult, calculate_streak, compute_new_badges, evaluate_escalation, build_cohort_dashboard

TODAY = date(2026, 3, 25)

def _ts(d):
    return datetime(d.year, d.month, d.day, 12, 0, 0, tzinfo=timezone.utc)

def _ci(status, d):
    return {"status": status, "checked_in_at": _ts(d)}

def test_no_checkins():
    r = calculate_streak([], today=TODAY)
    assert r.current_streak == 0

def test_yesterday_streak_1():
    r = calculate_streak([_ci("confirmed", TODAY - timedelta(days=1))], today=TODAY)
    assert r.current_streak == 1

def test_three_consecutive():
    cis = [_ci("confirmed", TODAY - timedelta(days=i)) for i in range(3)]
    assert calculate_streak(cis, today=TODAY).current_streak == 3

def test_gap_breaks():
    cis = [_ci("confirmed", TODAY - timedelta(days=1)), _ci("confirmed", TODAY - timedelta(days=3))]
    assert calculate_streak(cis, today=TODAY).current_streak == 1

def test_missed_ignored():
    cis = [_ci("missed", TODAY - timedelta(days=1))]
    assert calculate_streak(cis, today=TODAY).current_streak == 0

def test_longest_streak():
    long = [_ci("confirmed", TODAY - timedelta(days=i)) for i in range(1, 6)]
    short = [_ci("confirmed", TODAY - timedelta(days=10)), _ci("confirmed", TODAY - timedelta(days=11))]
    r = calculate_streak(long + short, today=TODAY)
    assert r.longest_streak == 5

def test_first_checkin_badge():
    sr = StreakResult(1, 1, 1, TODAY)
    badges = compute_new_badges(sr, set(), today=TODAY)
    assert any(b.badge_id == "first_checkin" for b in badges)

def test_no_duplicate_badge():
    sr = StreakResult(7, 7, 7, TODAY)
    badges = compute_new_badges(sr, {"first_checkin", "streak_3", "streak_7"}, today=TODAY)
    assert not any(b.badge_id == "streak_7" for b in badges)

def test_streak_3_and_7():
    sr = StreakResult(7, 7, 7, TODAY)
    ids = {b.badge_id for b in compute_new_badges(sr, set(), today=TODAY)}
    assert "streak_3" in ids and "streak_7" in ids

def test_zero_no_badge():
    sr = StreakResult(0, 0, 0, None)
    assert compute_new_badges(sr, set(), today=TODAY) == []

def test_no_misses_ok():
    r = evaluate_escalation([_ci("confirmed", TODAY - timedelta(days=1))], today=TODAY)
    assert r.level == "none"

def test_one_miss_grace():
    r = evaluate_escalation([_ci("missed", TODAY - timedelta(days=2))], today=TODAY)
    assert r.level == "none"

def test_two_misses_nudge():
    cis = [_ci("missed", TODAY - timedelta(days=i)) for i in range(1, 3)]
    assert evaluate_escalation(cis, today=TODAY).level == "nudge"

def test_three_misses_escalate():
    cis = [_ci("missed", TODAY - timedelta(days=i)) for i in range(1, 4)]
    assert evaluate_escalation(cis, today=TODAY).level == "escalate"

def test_old_miss_ignored():
    r = evaluate_escalation([_ci("missed", TODAY - timedelta(days=10))], today=TODAY)
    assert r.recent_misses == 0

def test_dashboard_empty():
    d = build_cohort_dashboard("c1", {}, {}, today=TODAY)
    assert d.total_members == 0

def test_dashboard_single():
    cis = [_ci("confirmed", TODAY - timedelta(days=i)) for i in range(3)]
    d = build_cohort_dashboard("c1", {"u1": cis}, {}, today=TODAY)
    assert d.students[0].streak.current_streak == 3

def test_dashboard_escalation():
    ci_b = [_ci("missed", TODAY - timedelta(days=i)) for i in range(1, 3)]
    d = build_cohort_dashboard("c1", {"b": ci_b}, {}, today=TODAY)
    assert d.students[0].escalation.level == "nudge"
