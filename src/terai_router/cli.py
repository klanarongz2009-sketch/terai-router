"""terai command line.

  terai "เส็ดหรือยัง"          one line: intent, confidence, normalized text
  terai --json "ช้วยบวก 2+3"   JSON output with the top 3 intents
  echo "ทำต่อ" | terai -        read lines from stdin (one result per line)
  terai                         interactive prompt (Ctrl-D to quit)
  terai chat                    chat that answers and remembers (session in ~/.terai/session.json)
  terai chat --session s.json   use another session file; --reset starts from an empty memory
"""
import argparse
import json
import os
import sys

from . import __version__, route


def _emit(text, as_json, threshold):
    r = route(text)
    intent = r['intent'] if r['confidence'] >= threshold else 'unknown'
    if as_json:
        print(json.dumps({'text': text, 'intent': intent, 'confidence': round(r['confidence'], 4),
                          'normalized': r['normalized'], 'coverage': round(r['coverage'], 3),
                          'top': [[k, round(v, 4)] for k, v in r['ranking']]}, ensure_ascii=False))
    else:
        print(f"{intent}\t{r['confidence']:.2f}\t{r['normalized']}")


DEFAULT_SESSION = os.path.join('~', '.terai', 'session.json')


def chat_main(argv=None):
    ap = argparse.ArgumentParser(prog='terai chat', description='TER-AI chat: offline Thai chat with memory (made with Sesame)')
    ap.add_argument('--session', default=DEFAULT_SESSION, help='session JSON file (default: ~/.terai/session.json)')
    ap.add_argument('--reset', action='store_true', help='erase the session memory before starting')
    a = ap.parse_args(argv)
    from .chat import Chat
    c = Chat(path=a.session)
    if a.reset:
        c.forget()
    tty = sys.stdin.isatty()
    if tty:
        print('TER-AI chat ' + __version__ + ' (offline). Session: ' + c.path + '. Ctrl-D or /quit to exit.')
    try:
        while True:
            line = input('you> ' if tty else '')
            line = line.strip()
            if not line:
                continue
            if line in ('/quit', '/exit'):
                break
            if not tty:
                print('you> ' + line)
            print('terai> ' + c.reply(line), flush=True)
    except (EOFError, KeyboardInterrupt):
        if tty:
            print()
    return 0


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    if argv and argv[0] == 'chat':
        return chat_main(argv[1:])
    ap = argparse.ArgumentParser(prog='terai', description='TER-AI: offline Thai intent router that tolerates typos (made with Sesame)')
    ap.add_argument('text', nargs='*', help="text to classify; '-' reads lines from stdin")
    ap.add_argument('--json', action='store_true', help='print JSON')
    ap.add_argument('--threshold', type=float, default=0.0, help="below this confidence print 'unknown'")
    ap.add_argument('--version', action='version', version=f'terai-router {__version__}')
    a = ap.parse_args(argv)
    if a.text == ['-']:
        for line in sys.stdin:
            if line.strip():
                _emit(line.strip(), a.json, a.threshold)
        return 0
    if a.text:
        _emit(' '.join(a.text), a.json, a.threshold)
        return 0
    try:
        while True:
            line = input('terai> ').strip()
            if line:
                _emit(line, a.json, a.threshold)
    except (EOFError, KeyboardInterrupt):
        print()
    return 0


if __name__ == '__main__':
    sys.exit(main())
