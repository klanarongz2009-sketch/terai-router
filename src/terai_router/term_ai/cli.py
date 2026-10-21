"""`terai term`: run TERM AI, the original Terminal AI (limited-time trial).

  terai term                      interactive mode (type 'exit', 'quit' or 'ออก' to quit)
  terai term "สวัสดี"              one message, one reply
  terai term --memory PATH        memory file (default ~/.terai/term_ai.json); --reset clears it
  terai term --config FILE        JSON with the original config keys (bot_name, greetings, ...)
  terai term --debug              show which rule or model intent answered
  terai term --trial-info         print the trial end and exit

Before 2027-01-01 00:00:00 Asia/Bangkok (UTC+7) a one-line notice with that end time goes to
stderr, then TERM AI runs. At or after it, `terai term` (with any arguments) prints that the
trial ended and exits with code 3, without reading or writing the memory file.
"""
import argparse
import os
import sys
from datetime import datetime, timezone

from .trial import EXIT_TRIAL_ENDED, TRIAL_END_TEXT, TrialEnded, ended_message, notice_line, trial_active

DEFAULT_MEMORY = os.path.join('~', '.terai', 'term_ai.json')
EXIT_WORDS = ('exit', 'quit', 'ออก')


def _ended():
    print(ended_message(), file=sys.stderr)
    return EXIT_TRIAL_ENDED


def main(argv=None, clock=None):
    """clock: callable returning a timezone-aware datetime (tests inject it)."""
    clock = clock or (lambda: datetime.now(timezone.utc))
    argv = sys.argv[1:] if argv is None else list(argv)
    if not trial_active(clock()):
        return _ended()
    ap = argparse.ArgumentParser(
        prog='terai term',
        description='TERM AI: the original Terminal AI (rules + the TER-AI-0.5 intent model), offline. '
                    f'Limited-time trial: stops working at {TRIAL_END_TEXT} and will be removed then.')
    ap.add_argument('text', nargs='*', help='one message; without it, interactive mode')
    ap.add_argument('--memory', default=DEFAULT_MEMORY, help=f'memory file (default {DEFAULT_MEMORY})')
    ap.add_argument('--reset', action='store_true', help='clear the memory before starting')
    ap.add_argument('--config', default=None, help='JSON file with config keys (bot_name, greetings, ...)')
    ap.add_argument('--seed', type=int, default=None, help='seed for random replies')
    ap.add_argument('--debug', action='store_true', help='append [rule] or [model: intent p= cov=] to replies')
    ap.add_argument('--trial-info', action='store_true', help='print the trial end time and exit')
    a = ap.parse_args(argv)
    print(notice_line(clock()), file=sys.stderr)
    if a.trial_info:
        return 0
    from .bot import TermAI, load_config
    try:
        cfg = load_config(a.config)
    except (OSError, ValueError) as e:
        ap.error(f'cannot read --config: {e}')
    debug = a.debug or os.environ.get('TERM_AI_DEBUG') == '1' or None
    try:
        bot = TermAI(memory_path=os.path.expanduser(a.memory), config=cfg, clock=clock, seed=a.seed, debug=debug)
        if a.reset:
            bot.h_forget()
            bot.save()
        if a.text:
            print(f'{bot.bot}> ' + bot.reply(' '.join(a.text)))
            bot.save()
            return 0
        tty = sys.stdin.isatty()
        print(f'{bot.bot}' + (f" | {cfg['tagline']}" if cfg['tagline'] else ''))
        print("พร้อม พิมพ์ 'ช่วย' ดูคำสั่ง, 'ออก' เพื่อจบ")
        while True:
            try:
                text = input(f"{cfg['user_prompt']}> " if tty else '')
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if text.strip().lower() in EXIT_WORDS:
                break
            if text.strip():
                print(f'{bot.bot}> ' + bot.reply(text), flush=True)
                bot.save()
        print('จบการทำงาน')
        return 0
    except TrialEnded:
        # the end time passed while TERM AI was running (for example in a long interactive session)
        return _ended()


if __name__ == '__main__':
    sys.exit(main())
