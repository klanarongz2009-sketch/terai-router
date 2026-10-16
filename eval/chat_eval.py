"""Run a frozen chat eval file through terai_router.Chat and score it.

    python eval/chat_eval.py [eval/chat_eval_v08.json] [--json out.json] [-v]

Each conversation runs in a fresh Chat with its own session file in a temp dir, the clock
fixed at the file's 'now' and the random seed at 'seed'. A turn with 'restart' saves the
session and loads a new Chat from the same file before the turn is sent.
"""
import argparse
import json
import os
import re
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'src'))

from terai_router import Chat  # noqa: E402


def check(turn, reply):
    """-> list of failed checks (empty = pass); None when the turn has no checks."""
    keys = [k for k in ('expect_all', 'expect_any', 'expect_none', 'expect_regex') if k in turn]
    if not keys:
        return None
    bad = []
    for s in turn.get('expect_all', []):
        if s not in reply:
            bad.append('missing ' + repr(s))
    if 'expect_any' in turn and not any(s in reply for s in turn['expect_any']):
        bad.append('none of ' + repr(turn['expect_any']))
    for s in turn.get('expect_none', []):
        if s in reply:
            bad.append('has ' + repr(s))
    if 'expect_regex' in turn and not re.search(turn['expect_regex'], reply):
        bad.append('no match ' + repr(turn['expect_regex']))
    return bad


def run(path, verbose=False):
    with open(path, encoding='utf-8') as fh:
        spec = json.load(fh)
    rows, cats = [], {}
    with tempfile.TemporaryDirectory() as tmp:
        for conv in spec['conversations']:
            sess = os.path.join(tmp, conv['id'] + '.json')
            chat = Chat(path=sess, now=spec['now'], seed=spec['seed'])
            for i, turn in enumerate(conv['turns']):
                if turn.get('restart'):
                    chat.save()
                    chat = Chat(path=sess, now=spec['now'], seed=spec['seed'])
                reply = chat.reply(turn['user'])
                bad = check(turn, reply)
                row = {'conv': conv['id'], 'category': conv['category'], 'turn': i, 'user': turn['user'],
                       'reply': reply, 'scored': bad is not None, 'pass': bad == [], 'fail': bad or []}
                rows.append(row)
                if bad is not None:
                    c = cats.setdefault(conv['category'], [0, 0])
                    c[1] += 1
                    c[0] += 1 if not bad else 0
                if verbose or bad:
                    mark = '  ' if bad is None else ('OK' if not bad else 'XX')
                    print(mark, conv['id'], i, turn['user'], '->', reply)
                    if bad:
                        print('     ', '; '.join(bad))
    scored = [r for r in rows if r['scored']]
    passed = sum(r['pass'] for r in scored)
    convs = {}
    for r in scored:
        convs.setdefault(r['conv'], True)
        convs[r['conv']] &= r['pass']
    return {'file': os.path.basename(path), 'turns_scored': len(scored), 'turns_passed': passed,
            'conversations': len(convs), 'conversations_passed': sum(convs.values()),
            'by_category': {k: {'passed': v[0], 'scored': v[1]} for k, v in sorted(cats.items())}, 'rows': rows}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('file', nargs='?', default=os.path.join(HERE, 'chat_eval_v08.json'))
    ap.add_argument('--json', help='write the full result here')
    ap.add_argument('-v', '--verbose', action='store_true')
    a = ap.parse_args(argv)
    res = run(a.file, a.verbose)
    print('turns %d/%d  conversations %d/%d' % (res['turns_passed'], res['turns_scored'],
                                              res['conversations_passed'], res['conversations']))
    for k, v in res['by_category'].items():
        print('  %-14s %d/%d' % (k, v['passed'], v['scored']))
    if a.json:
        with open(a.json, 'w', encoding='utf-8') as fh:
            json.dump(res, fh, ensure_ascii=False, indent=1)
    return 0 if res['turns_passed'] == res['turns_scored'] else 1


if __name__ == '__main__':
    sys.exit(main())
