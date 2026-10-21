"""terai muml-wa: write a song with MuML 1.0 WA and save it as a .mid file (the browser demo plays it with Web Audio)."""
from __future__ import annotations

import argparse
import json
import sys
import time


def main(argv=None) -> int:
    from . import generate, to_midi, writer_available
    from . import net
    ap = argparse.ArgumentParser(prog='terai muml-wa', description='MuML 1.0 WA: notes from the MuML 1.0 network '
                                 '(Markov v1 fallback), saved as MIDI')
    ap.add_argument('prompt', nargs='*', help='Thai or English, e.g. "rock E minor 120 bpm 30 วินาที"')
    ap.add_argument('--seed', type=int, default=0)
    ap.add_argument('--style', default='auto', choices=['auto', 'folk', 'rock'])
    ap.add_argument('--writer', default='auto', choices=['auto', 'net', 'markov'],
                    help='net = trained MuML 1.0 network, markov = Markov v1, auto = net when its weights are installed')
    ap.add_argument('--setup', action='store_true', help=f'download the MuML 1.0 weights ({net.WEIGHTS_BYTES:,} bytes) '
                    'and check the SHA-256 (needs numpy to run them)')
    ap.add_argument('-o', '--out', default='muml-wa.mid')
    ap.add_argument('--json', action='store_true', help='print the song (tokens, notes) as JSON')
    a = ap.parse_args(argv)
    if a.setup:
        print(net.setup())
        if not net.numpy_available():
            print('numpy is not installed: pip install numpy (without it the Markov v1 writer is used)', file=sys.stderr)
        if not a.prompt:
            return 0
    writer = a.writer
    if writer == 'auto':
        writer = writer_available()
        if writer == 'markov':
            print('terai muml-wa: MuML 1.0 weights or numpy missing, using Markov v1 (run --setup)', file=sys.stderr)
    t0 = time.time()
    song = generate(' '.join(a.prompt), a.seed, a.style, writer=writer)
    with open(a.out, 'wb') as f:
        f.write(to_midi(song))
    if a.json:
        print(json.dumps(song, ensure_ascii=False))
    else:
        p = song['prompt']
        print(f"{a.out}: {song['note_writer']} | {p['style']} {p['meter']} key {p['tonic']} {p['mode']} {p['bpm']} BPM | "
              f"{len(song['tokens'])} tokens | {time.time() - t0:.1f} s")
    return 0


if __name__ == '__main__':
    sys.exit(main())
