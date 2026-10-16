"""terai command line.

  terai "เส็ดหรือยัง"          one line: intent, confidence, normalized text
  terai --json "ช้วยบวก 2+3"   JSON output with the top 3 intents
  echo "ทำต่อ" | terai -        read lines from stdin (one result per line)
  terai                         interactive prompt (Ctrl-D to quit)
"""
import argparse
import json
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


def main(argv=None):
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
