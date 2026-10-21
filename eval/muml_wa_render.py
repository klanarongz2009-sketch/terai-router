"""Render MuML 1.0 WA samples with the real Web Audio API in headless Chromium and measure it.

Loads the built demo (docs/index.html), opens the MuML tab, then inside the page:
  * times MUMLWA.generate() (notes only) over several runs,
  * renders each sample with OfflineAudioContext (the same code as the Download .wav button),
  * returns the WAV bytes, which ffmpeg turns into .mp3.
Also checks that the page's song equals the Python reference for the same prompt and seed.

usage: python eval/muml_wa_render.py --out DIR [--runs 20]
"""
from __future__ import annotations

import argparse
import base64
import gzip
import json
import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from terai_router import muml_wa  # noqa: E402

SAMPLES = [
    ('01-folk-jig', 'เพลงโฟล์คสนุกๆ จิ๊ก 30 วินาที', 1, 'auto'),
    ('02-rock-eminor', 'เพลงร็อกมันส์ๆ 140 bpm คีย์ E minor 30 วินาที', 1, 'auto'),
    ('03-rock-reel', 'rock reel key of D 120 bpm 30 seconds', 2, 'auto'),
    ('04-folk-sad-waltz', 'เพลงเศร้า วอลทซ์ คีย์ A minor 30 วินาที', 3, 'auto'),
]

PAGE_JS = """
async ([samples, runs]) => {
  const out = [];
  for (const [name, prompt, seed, style] of samples) {
    let song, t0 = performance.now();
    for (let i = 0; i < runs; i++) song = MUMLWA.generate(prompt, seed, style);
    const genMs = (performance.now() - t0) / runs;
    const t1 = performance.now();
    const buf = await MUMLWA.renderBuffer(song, 44100);
    const renderMs = performance.now() - t1;
    let peak = 0, sum = 0;
    for (let c = 0; c < buf.numberOfChannels; c++) { const d = buf.getChannelData(c); for (let i = 0; i < d.length; i++) { const a = Math.abs(d[i]); if (a > peak) peak = a; sum += d[i] * d[i]; } }
    const wav = MUMLWA.wavBytes(buf);
    let bin = ''; for (let i = 0; i < wav.length; i += 0x8000) bin += String.fromCharCode.apply(null, wav.subarray(i, i + 0x8000));
    const notes = song.tracks.reduce((a, t) => a + t.notes.length, 0);
    out.push({ name, prompt, seed, style, genMs, renderMs, seconds: buf.duration, peak, rms: Math.sqrt(sum / (buf.length * buf.numberOfChannels)),
               notes, song, wav: btoa(bin) });
  }
  return out;
}
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--runs', type=int, default=20)
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    index = ROOT / 'docs' / 'index.html'
    js = (ROOT / 'docs' / 'muml_wa.js').read_bytes()
    table = (ROOT / 'src' / 'terai_router' / 'muml_wa' / 'data' / 'markov.json').read_bytes()
    report = {'js_bytes': len(js), 'js_gzip_bytes': len(gzip.compress(js, 9)),
              'table_bytes': len(table), 'table_gzip_bytes': len(gzip.compress(table, 9)), 'samples': []}
    errors = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=['--autoplay-policy=no-user-gesture-required'])
        page = browser.new_page(viewport={'width': 800, 'height': 1100})
        page.on('pageerror', lambda e: errors.append(str(e)))
        t0 = time.time()
        page.goto(index.as_uri() + '#muml')
        page.wait_for_function('window.MUMLWA && document.getElementById("mu-info").textContent.length > 1')
        report['page_ready_s'] = round(time.time() - t0, 2)
        report['tab_visible'] = page.is_visible('#pane-muml')
        report['tab_info'] = page.text_content('#mu-info')
        report['body_bg'] = page.evaluate('getComputedStyle(document.body).backgroundColor')
        page.screenshot(path=str(a.out / 'muml-tab.png'), full_page=False)
        report['user_agent'] = page.evaluate('navigator.userAgent')
        res = page.evaluate(PAGE_JS, [SAMPLES, a.runs])
        browser.close()
    for r in res:
        wav = a.out / f"{r['name']}.wav"
        wav.write_bytes(base64.b64decode(r.pop('wav')))
        mp3 = wav.with_suffix('.mp3')
        subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', str(wav), '-codec:a', 'libmp3lame', '-b:a', '192k', str(mp3)], check=True)
        song = r.pop('song')
        py = json.loads(json.dumps(muml_wa.generate(r['prompt'], r['seed'], r['style']), ensure_ascii=False))
        r['matches_python'] = py == song
        r['reading'] = song['prompt']
        r['form'] = song['form']
        r['mp3'] = str(mp3)
        r['mp3_bytes'] = mp3.stat().st_size
        wav.unlink()
        report['samples'].append(r)
    report['page_errors'] = errors
    (a.out / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
