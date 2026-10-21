"""TERM AI: the original Terminal AI that TER-AI grew from, as a LIMITED-TIME TRIAL.

TERM AI was the first program of the project (2026-10-10, on the development VM): a Thai
terminal chatbot made of regex rules plus the first own model, the TER-AI-0.5 intent
classifier (character n-gram Naive Bayes, 149 samples, 11 intents). It is shipped in
v0.14.0 so people can try it, and it works only until

    2027-01-01 00:00:00 Asia/Bangkok (UTC+7)

At or after that moment `terai term` prints a message and exits with code 3, and the
library raises TrialEnded. TERM AI is then removed from the repository: see REMOVAL_PATHS in
trial.py and docs/TERM-AI.md ("Removal"). Nothing else in terai_router imports this package.

    >>> from datetime import datetime
    >>> from terai_router.term_ai import TermAI, BANGKOK
    >>> bot = TermAI(clock=lambda: datetime(2026, 12, 1, 9, 0, tzinfo=BANGKOK))
    >>> bot.reply('คำนวณ (12+8)*3')
    '(12+8)*3 = 60'
"""
from .trial import (BANGKOK, EXIT_TRIAL_ENDED, REMOVAL_EDITS, REMOVAL_PATHS, TRIAL_END, TRIAL_END_TEXT,
                    TrialEnded, check_trial, ended_message, notice_line, time_left, trial_active)

__all__ = ['TermAI', 'DEFAULTS', 'load_config', 'BANGKOK', 'TRIAL_END', 'TRIAL_END_TEXT', 'EXIT_TRIAL_ENDED',
           'REMOVAL_PATHS', 'REMOVAL_EDITS', 'TrialEnded', 'check_trial', 'ended_message', 'notice_line',
           'time_left', 'trial_active']


def __getattr__(name):
    # bot (and the model) load lazily, so `python -m terai_router.term_ai.intent_model` runs cleanly
    if name in ('TermAI', 'DEFAULTS', 'load_config'):
        from . import bot
        return getattr(bot, name)
    raise AttributeError(f'module {__name__!r} has no attribute {name!r}')
