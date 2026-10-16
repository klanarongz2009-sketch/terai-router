"""Record the MediaWiki API responses that eval/chat_web_v09.json needs (real network, run once, then frozen).

Usage: python eval/make_web_fixtures.py   -> eval/web_fixtures_v09.json
Keys are "<host>|<gsrsearch>" so the JS and Python request URLs (JS adds origin=*) map to the same response.
"""
import json
import pathlib
import sys
import tempfile
import urllib.parse

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from terai_router.chat import Chat  # noqa: E402
from terai_router.websearch import WebSearch  # noqa: E402


def key(url):
    u = urllib.parse.urlparse(url)
    q = urllib.parse.parse_qs(u.query)
    return u.netloc + '|' + q.get('gsrsearch', [''])[0]


def main():
    spec = json.loads((ROOT / 'eval' / 'chat_web_v09.json').read_text(encoding='utf-8'))
    real = WebSearch(enabled=True, cache_dir=None)
    fixtures = {}

    def record(url):
        data = real.get(url)
        fixtures[key(url)] = data
        return data

    for conv in spec['conversations']:
        if conv.get('offline'):
            continue
        with tempfile.TemporaryDirectory() as d:
            path = pathlib.Path(d) / 's.json'
            mk = lambda: Chat(path, now=spec['now'], seed=spec['seed'],  # noqa: E731
                              websearch=WebSearch(enabled=True, cache_dir=None, fetch=record))
            chat = mk()
            for t in conv['turns']:
                if t.get('restart'):
                    chat = mk()
                print(t['user'], '->', chat.reply(t['user'])[:160])
    out = ROOT / 'eval' / 'web_fixtures_v09.json'
    out.write_text(json.dumps({'retrieved': '2026-10-16', 'license': 'Wikipedia text, CC BY-SA 4.0', 'responses': fixtures},
                              ensure_ascii=False, sort_keys=True), encoding='utf-8')
    print('responses:', len(fixtures), 'bytes:', out.stat().st_size)


if __name__ == '__main__':
    main()
