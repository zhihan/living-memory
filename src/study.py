"""Study gamification: streak calculation, badge award logic, escalation rules.

This module operates on pure data (CheckIn lists, streak snapshots) and has no
Firestore dependency — all persistence is delegated to study_storage.py.

Streak rules
------------
- A *study day* is any calendar day (in the workspace timezone) where the user
  has at least one check-in with status "confirmed".
- The streak counter increments when consecutive days each have a confirmed
  check-in.  A single missed day resets the counter to 0.
- "Today" is not penalised: if the user has not yet checked in today we keep
  the streak from yesterday rather than resetting it.

Badge rules
-----------
Badges are awarded when the streak reaches a threshold for the first time.
Currently defined thresholds:

  streak_3   — 3-day streak
  streak_7   — 7-day streak
  streak_14  — 14-day streak
  streak_30  — 30-day streak
  streak_60  — 60-day streak
  streak_100 — 100-day streak
  first_checkin — first ever confirmed check-in

Escalation rules
----------------
A missed study event is one where an occurrence whose scheduled_for date has
passed and the user's check-in status is "missed" (or the user has no check-in
at all).

Escalation levels:
  1 miss  → no action (grace)
  2 misses in 7 days → "nudge" alert
  3+ misses in 7 days → "escalate" alert for teacher review
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone, timedelta
from typing import Sequence


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class StreakResult:
    """Output of calculate_streak()."""
    current_streak: int
    longest_streak: int
    total_confirmed: int
    # Last calendar day on which a confirmed check-in exists (may be None)
    last_confirmed_date: date | None


@dataclass
class BadgeAward:
    badge_id: str
    label: str
    awarded_on: date


@dataclass
class EscalationResult:
    level: str  # "none" | "nudge" | "escalate"
    recent_misses: int  # misses in the last 7 days
    message: str


# ---------------------------------------------------------------------------
# Streak calculation
# ---------------------------------------------------------------------------

def calculate_streak(
    check_ins: Sequence[dict],
    tz_name: str = "UTC",
    today: date | None = None,
) -> StreakResult:
    """Compute streak stats from a list of check-in dicts.

    Each dict must contain at least:
      - ``status``: str  ("confirmed" | "missed" | ...)
      - ``checked_in_at``: datetime | None

    Args:
        check_ins: Iterable of check-in dicts (may include non-confirmed entries).
        tz_name: IANA timezone name used to convert UTC timestamps to local dates.
        today: Override for "today" (used in tests).

    Returns:
        StreakResult with current_streak, longest_streak, total_confirmed, and
        last_confirmed_date.
    """
    import zoneinfo

    try:
        tz = zoneinfo.ZoneInfo(tz_name)
    except Exception:
        tz = timezone.utc  # type: ignore[assignment]

    if today is None:
        today = datetime.now(timezone.utc).astimezone(tz).date()

    # Collect the set of local calendar dates with a confirmed check-in
    confirmed_dates: set[date] = set()
    for ci in check_ins:
        if ci.get("status") != "confirmed":
            continue
        ts = ci.get("checked_in_at")
        if ts is None:
            continue
        if isinstance(ts, datetime):
            local_dt = ts.astimezone(tz)
        else:
            # Assume it's already a date-like
            local_dt = datetime.fromisoformat(str(ts)).astimezone(tz)
        confirmed_dates.add(local_dt.date())

    total_confirmed = len(confirmed_dates)
    last_confirmed_date = max(confirmed_dates) if confirmed_dates else None

    if not confirmed_dates:
        return StreakResult(
            current_streak=0,
            longest_streak=0,
            total_confirmed=0,
            last_confirmed_date=None,
        )

    # Walk backwards from yesterday (don't penalise today if no check-in yet)
    current_streak = 0
    check_day = today - timedelta(days=1)
    if today in confirmed_dates:
        # today already has a check-in — start from today
        check_day = today

    while check_day in confirmed_dates:
        current_streak += 1
        check_day -= timedelta(days=1)

    # Compute longest streak by sorting all confirmed dates
    sorted_dates = sorted(confirmed_dates)
    longest = 1
    run = 1
    for i in range(1, len(sorted_dates)):
        if (sorted_dates[i] - sorted_dates[i - 1]).days == 1:
            run += 1
            longest = max(longest, run)
        else:
            run = 1

    return StreakResult(
        current_streak=current_streak,
        longest_streak=longest,
        total_confirmed=total_confirmed,
        last_confirmed_date=last_confirmed_date,
    )


# ---------------------------------------------------------------------------
# Badge logic
# ---------------------------------------------------------------------------

# (threshold, badge_id, label)
_STREAK_BADGES: list[tuple[int, str, str]] = [
    (3,   "streak_3",   "3-Day Streak 🔥"),
    (7,   "streak_7",   "Week Warrior 🗓️"),
    (14,  "streak_14",  "Fortnight Focus 📚"),
    (30,  "streak_30",  "Monthly Master 🏅"),
    (60,  "streak_60",  "Two-Month Titan 💪"),
    (100, "streak_100", "Century Scholar 🎓"),
]

_FIRST_CHECKIN_BADGE = BadgeAward(
    badge_id="first_checkin",
    label="First Check-In ✅",
    awarded_on=date.today(),
)


def compute_new_badges(
    streak_result: StreakResult,
    existing_badge_ids: set[str],
    today: date | None = None,
) -> list[BadgeAward]:
    """Return any badges newly earned given the current streak and history.

    Args:
        streak_result: Output of calculate_streak().
        existing_badge_ids: Badges the user already holds (by badge_id).
        today: Override for "today" (used in tests).

    Returns:
        List of new BadgeAward objects.  Empty if nothing new was earned.
    """
    if today is None:
        today = date.today()

    new_badges: list[BadgeAward] = []

    # First check-in badge
    if streak_result.total_confirmed >= 1 and "first_checkin" not in existing_badge_ids:
        new_badges.append(BadgeAward(
            badge_id="first_checkin",
            label=_FIRST_CHECKIN_BADGE.label,
            awarded_on=today,
        ))

    # Streak-based badges
    current = streak_result.current_streak
    for threshold, badge_id, label in _STREAK_BADGES:
        if current >= threshold and badge_id not in existing_badge_ids:
            new_badges.append(BadgeAward(
                badge_id=badge_id,
                label=label,
                awarded_on=today,
            ))

    return new_badges


# ---------------------------------------------------------------------------
# Escalation rules
# ---------------------------------------------------------------------------

def evaluate_escalation(
    check_ins: Sequence[dict],
    tz_name: str = "UTC",
    today: date | None = None,
    window_days: int = 7,
) -> EscalationResult:
    """Evaluate escalation level based on recent missed check-ins.

    A "miss" is a check-in with status "missed".  We count how many fall
    within the last ``window_days`` calendar days.

    Levels:
      0–1 misses → "none"
      2 misses   → "nudge"
      3+ misses  → "escalate"

    Args:
        check_ins: All check-in dicts for this student in this series/workspace.
        tz_name: Timezone for determining "recent".
        today: Override for "today" (used in tests).
        window_days: How many days back to look (default 7).

    Returns:
        EscalationResult.
    """
    import zoneinfo

    try:
        tz = zoneinfo.ZoneInfo(tz_name)
    except Exception:
        tz = timezone.utc  # type: ignore[assignment]

    if today is None:
        today = datetime.now(timezone.utc).astimezone(tz).date()

    cutoff = today - timedelta(days=window_days)
    recent_misses = 0

    for ci in check_ins:
        if ci.get("status") != "missed":
            continue
        ts = ci.get("checked_in_at") or ci.get("created_at")
        if ts is None:
            continue
        if isinstance(ts, datetime):
            local_date = ts.astimezone(tz).date()
        else:
            local_date = datetime.fromisoformat(str(ts)).astimezone(tz).date()
        if local_date >= cutoff:
            recent_misses += 1

    if recent_misses >= 3:
        level = "escalate"
        message = f"{recent_misses} missed sessions in the past {window_days} days — teacher review recommended."
    elif recent_misses == 2:
        level = "nudge"
        message = f"{recent_misses} missed sessions in the past {window_days} days — consider sending a reminder."
    else:
        level = "none"
        message = "No escalation needed."

    return EscalationResult(level=level, recent_misses=recent_misses, message=message)


# ---------------------------------------------------------------------------
# Dashboard aggregation
# ---------------------------------------------------------------------------

@dataclass
class StudentSummary:
    user_id: str
    streak: StreakResult
    escalation: EscalationResult
    badges: list[str]  # badge_ids already awarded


@dataclass
class CohortDashboard:
    cohort_id: str
    total_members: int
    students: list[StudentSummary]
    # Aggregate stats
    avg_current_streak: float
    total_misses_this_week: int


def build_cohort_dashboard(
    cohort_id: str,
    member_check_ins: dict[str, list[dict]],
    member_badges: dict[str, list[str]],
    tz_name: str = "UTC",
    today: date | None = None,
) -> CohortDashboard:
    """Build a teacher-facing dashboard for a cohort.

    Args:
        cohort_id: The cohort identifier.
        member_check_ins: Mapping of user_id → list of check-in dicts.
        member_badges: Mapping of user_id → list of badge_ids already awarded.
        tz_name: Workspace timezone.
        today: Override for today (used in tests).

    Returns:
        CohortDashboard with per-student summaries and aggregate stats.
    """
    students: list[StudentSummary] = []
    total_misses = 0

    for uid, check_ins in member_check_ins.items():
        streak = calculate_streak(check_ins, tz_name=tz_name, today=today)
        escalation = evaluate_escalation(check_ins, tz_name=tz_name, today=today)
        badges = member_badges.get(uid, [])
        students.append(StudentSummary(
            user_id=uid,
            streak=streak,
            escalation=escalation,
            badges=badges,
        ))
        total_misses += escalation.recent_misses

    avg_streak = (
        sum(s.streak.current_streak for s in students) / len(students)
        if students else 0.0
    )

    return CohortDashboard(
        cohort_id=cohort_id,
        total_members=len(students),
        students=students,
        avg_current_streak=round(avg_streak, 2),
        total_misses_this_week=total_misses,
    )
