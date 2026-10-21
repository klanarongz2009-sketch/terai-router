"""Time limit of the TERM AI trial.

TERM AI is a limited-time trial. It runs before 2027-01-01 00:00:00 Asia/Bangkok (UTC+7)
and refuses to run at or after that moment. Thailand has no daylight saving time, so a
fixed UTC+7 offset is exact and needs no tz database (works on Python 3.9, Windows too).

Every function takes an optional ``now`` (a timezone-aware datetime) so tests can inject
the clock. Without it the real clock is read in UTC.

REMOVAL at 2027-01-01 00:00:00 (UTC+7): TERM AI is deleted from the repository. The paths
to delete are listed in REMOVAL_PATHS below and in docs/TERM-AI.md ("Removal").
"""
from datetime import datetime, timedelta, timezone

BANGKOK = timezone(timedelta(hours=7), 'UTC+07:00')
TRIAL_END = datetime(2027, 1, 1, 0, 0, 0, tzinfo=BANGKOK)
TRIAL_END_TEXT = '2027-01-01 00:00:00 Asia/Bangkok (UTC+7)'
EXIT_TRIAL_ENDED = 3

# Paths (relative to the repository root) that the removal on 2027-01-01 deletes, plus the
# files where TERM AI is only mentioned and the mention must be taken out.
REMOVAL_PATHS = (
    'src/terai_router/term_ai/',
    'tests/test_term_ai.py',
    'docs/TERM-AI.md',
)
REMOVAL_EDITS = (
    'src/terai_router/cli.py',   # the `term` dispatch in main() and the docstring line
    'pyproject.toml',            # "term_ai/data/*.json" in package-data
    'README.md',                 # release-table row, TERM AI section, license-table row
    'README.th.md',              # the same in Thai
    'CHANGELOG.md',              # keep v0.14.0 history; add a removal entry
)


class TrialEnded(RuntimeError):
    """Raised when TERM AI is used at or after TRIAL_END."""


def _aware(now):
    if now is None:
        return datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError('now must be a timezone-aware datetime')
    return now


def trial_active(now=None):
    """True before 2027-01-01 00:00:00 UTC+7, False at that instant and after."""
    return _aware(now) < TRIAL_END


def time_left(now=None):
    """Time until the trial ends (timedelta(0) once it has ended)."""
    left = TRIAL_END - _aware(now)
    return left if left > timedelta(0) else timedelta(0)


def notice_line(now=None):
    """One-line notice printed before TERM AI runs."""
    left = time_left(now)
    if left >= timedelta(days=1):
        n = left.days
        rest = f'{n} day left' if n == 1 else f'{n} days left'
    else:
        rest = 'less than 1 day left'
    return (f'TERM AI is a limited-time trial: it stops working at {TRIAL_END_TEXT} and will be removed '
            f'from terai-router then ({rest}).')


def ended_message():
    """Message printed (to stderr) when TERM AI is run at or after the end."""
    return (f'TERM AI trial ended at {TRIAL_END_TEXT}. It no longer runs and is being removed from '
            f'terai-router. Use `terai chat` instead.')


def check_trial(now=None):
    """Raise TrialEnded at or after TRIAL_END."""
    if not trial_active(now):
        raise TrialEnded(ended_message())
