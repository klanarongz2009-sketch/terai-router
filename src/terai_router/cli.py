"""terai command line.

  terai "เส็ดหรือยัง"          one line: intent, confidence, normalized text
  terai --json "ช้วยบวก 2+3"   JSON output with the top 3 intents
  echo "ทำต่อ" | terai -        read lines from stdin (one result per line)
  terai                         interactive prompt (Ctrl-D to quit)
  terai chat                    chat that answers and remembers (session in ~/.terai/session.json)
  terai chat --session s.json   use another session file; --reset starts from an empty memory
  terai chat --web              opt-in web search (Wikipedia th, en); --searx URL adds a SearXNG instance
  terai chat --speak            also speak each reply with TTH (needs a TTH engine; plays it if a player exists)
  terai tth "ข้อความ" -o out.wav  TTH: Thai text-to-speech (Wayu local engine, edge-tts fallback)
  terai tth --dry-run "..."     print what TTH would say, chunk by chunk, without making audio
  terai temmo "idea" -o out     Temmo 1.0: build a complete small HTML5 game (BYOK; no key = local Gemma 4)
  terai muml --hiq "เพลงลูกทุ่ง 130 bpm" -o song.mp3  MUML 1.0 HIQ: text-to-music audio (ACE-Step 1.5, CPU)
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
DEFAULT_SPEAK_DIR = os.path.join('~', '.terai', 'tth')


def _voice_arg(ap):
    from .tth import DEFAULT_VOICE
    ap.add_argument('--voice', default=None,
                    help='Wayu voice (default %s; see terai tth --list-voices) or an edge-tts voice such as '
                         'th-TH-PremwadeeNeural' % DEFAULT_VOICE)
    ap.add_argument('--speed', type=float, default=1.0, help='speaking speed, 0.5 to 2.0 (default 1.0)')
    ap.add_argument('--engine', choices=['auto', 'wayu', 'edge'], default='auto',
                    help='auto (default): Wayu if installed, else edge-tts')
    ap.add_argument('--no-fallback', action='store_true', help='do not try the other engine when one fails')
    ap.add_argument('--polite', choices=['ครับ', 'ค่ะ'], default=None,
                    help='polite particle for replies: the male (ครับ) or female (ค่ะ) form (default: from the voice gender)')


def _make_tth(a):
    from .tth import TTH
    return TTH(engine=a.engine, voice=a.voice, speed=a.speed, polite=a.polite, fallback=not a.no_fallback)


def tth_main(argv=None):
    from . import tth as T
    ap = argparse.ArgumentParser(prog='terai tth',
                                 description='TTH: Thai text-to-speech for TER-AI. Local engine Wayu-Paxa-TTS-Edge '
                                             '(weights CC-BY-NC-4.0 by Paxa Labs, downloaded from Hugging Face on '
                                             'first use); fallback edge-tts (online Microsoft service).')
    ap.add_argument('text', nargs='*', help="text to speak; '-' reads stdin")
    ap.add_argument('-o', '--out', default='tth.wav', help='output file, .wav or .mp3 (default tth.wav)')
    ap.add_argument('-f', '--file', help='read the text from this UTF-8 file')
    _voice_arg(ap)
    ap.add_argument('--max-chars', type=int, default=T.MAX_CHARS, help='longest chunk (default %d)' % T.MAX_CHARS)
    ap.add_argument('--seed', type=int, default=0, help='Wayu sampling seed (default 0)')
    ap.add_argument('--dry-run', action='store_true', help='print the spoken text chunks, make no audio')
    ap.add_argument('--json', action='store_true', help='print the result as JSON')
    ap.add_argument('--list-voices', action='store_true', help='list voices and exit')
    ap.add_argument('--engines', action='store_true', help='show which engines are installed and exit')
    a = ap.parse_args(argv)
    if a.list_voices:
        print('wayu (local, CC-BY-NC-4.0 weights):')
        for v in T.WAYU_VOICES:
            print('  ' + v + ('  (default)' if v == T.DEFAULT_VOICE else ''))
        print('edge (online, Microsoft):')
        for v, g in T.EDGE_VOICES.items():
            print('  %s  (%s)' % (v, 'female' if g == 'f' else 'male'))
        return 0
    if a.engines:
        for k, v in T.installed_engines().items():
            print('%s\t%s' % (k, 'installed' if v else 'not installed'))
        return 0
    if a.file:
        with open(a.file, encoding='utf-8') as f:
            text = f.read()
    elif a.text == ['-']:
        text = sys.stdin.read()
    else:
        text = ' '.join(a.text)
    if not text.strip():
        ap.error('no text: give it as an argument, with -f FILE, or with - for stdin')
    try:
        t = _make_tth(a)
        t.max_chars, t.seed = a.max_chars, a.seed
        if a.dry_run:
            spoken, pieces = t.plan(text)
            if a.json:
                print(json.dumps({'text': spoken, 'chunks': pieces, 'polite': t.polite, 'engines': t.order()},
                                 ensure_ascii=False))
            else:
                for i, p in enumerate(pieces, 1):
                    print('%d\t%s' % (i, p))
            return 0
        r = t.synthesize(text, a.out)
    except ValueError as e:
        ap.error(str(e))
    except T.TTHError as e:
        print('terai tth: ' + str(e), file=sys.stderr)
        return 2
    if a.json:
        print(json.dumps(r, ensure_ascii=False))
    else:
        secs = '%.2f s' % r['seconds'] if r['seconds'] is not None else '? s'
        print('%s\t%s\tengine=%s voice=%s chunks=%d%s' % (r['out'], secs, r['engine'], r['voice'], r['chunks'],
                                                         ' (fallback)' if r['fallback_used'] else ''))
        for e in r['errors']:
            print('terai tth: skipped ' + e, file=sys.stderr)
    return 0


def _speak_reply(tth, text, folder, turn, player):
    import subprocess
    from .tth import TTHError, find_player
    os.makedirs(folder, exist_ok=True)
    out = os.path.join(folder, 'reply-%03d.wav' % turn)
    try:
        r = tth.synthesize(text, out)
    except (TTHError, ValueError) as e:
        print('[tth] ' + str(e), file=sys.stderr)
        return None
    cmd = player.split() if player else find_player()
    if cmd and player != 'none':
        subprocess.run(cmd + [out], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print('[tth] %s (%s)' % (out, r['engine']), file=sys.stderr)
    return r


def chat_main(argv=None):
    ap = argparse.ArgumentParser(prog='terai chat', description='TER-AI chat: offline Thai chat with memory (made with Sesame)')
    ap.add_argument('--session', default=DEFAULT_SESSION, help='session JSON file (default: ~/.terai/session.json)')
    ap.add_argument('--reset', action='store_true', help='erase the session memory before starting')
    ap.add_argument('--web', action='store_true',
                    help='opt-in web search: questions the offline pack cannot answer go to Wikipedia (th, then en)')
    ap.add_argument('--searx', metavar='URL', help='also ask this SearXNG instance (implies --web)')
    ap.add_argument('--speak', action='store_true', help='speak every reply with TTH (see terai tth --help)')
    ap.add_argument('--speak-dir', default=DEFAULT_SPEAK_DIR, help='where spoken replies are saved (default ~/.terai/tth)')
    ap.add_argument('--player', default=None,
                    help="command that plays a WAV file (default: first of ffplay, paplay, aplay, afplay, mpv, "
                         "termux-media-player); 'none' only saves the files")
    _voice_arg(ap)
    a = ap.parse_args(argv)
    from .chat import Chat
    c = Chat(path=a.session, web=a.web, searx=a.searx)
    tth = None
    if a.speak:
        try:
            tth = _make_tth(a)
        except ValueError as e:
            ap.error(str(e))
    turn = 0
    if a.reset:
        c.forget()
    tty = sys.stdin.isatty()
    if tty:
        print('TER-AI chat ' + __version__ + (' (web search on)' if c.web else ' (offline)') + (' (speaking with TTH)' if tth else '') + '. Session: ' + c.path + '. Ctrl-D or /quit to exit.')
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
            answer = c.reply(line)
            print('terai> ' + answer, flush=True)
            if tth is not None:
                turn += 1
                _speak_reply(tth, answer, os.path.expanduser(a.speak_dir), turn, a.player)
    except (EOFError, KeyboardInterrupt):
        if tty:
            print()
    return 0


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    if argv and argv[0] == 'chat':
        return chat_main(argv[1:])
    if argv and argv[0] == 'tth':
        return tth_main(argv[1:])
    if argv and argv[0] == 'temmo':
        from .temmo.cli import main as temmo_main
        return temmo_main(argv[1:])
    if argv and argv[0] == 'sankpup':
        from .sankpup.cli import main as sankpup_main
        return sankpup_main(argv[1:])
    if argv and argv[0] in ('muml', 'muml-hiq'):
        # Contract with MuML 1.0: see docs/MUML-CLI-CONTRACT.md. `--hiq` / `--model hiq`
        # (or the `muml-hiq` alias) goes to MUML 1.0 HIQ; everything else is MuML 1.0.
        from .muml_hiq.cli import is_hiq_request, main as muml_hiq_main
        if argv[0] == 'muml-hiq' or is_hiq_request(argv[1:]):
            return muml_hiq_main(argv[1:])
        try:
            from .muml.cli import main as muml_main
        except ImportError:
            print('terai muml: MuML 1.0 is not in this build; use --hiq for MUML 1.0 HIQ', file=sys.stderr)
            return 2
        return muml_main(argv[1:])
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
