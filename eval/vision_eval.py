"""TERAI1 (beta) image reading: a fixed set of generated test images (eval/vision/*.png, made by --make).

    python eval/vision_eval.py --make          # (re)draw the images (needs Pillow, the TLWG Loma Thai font and DejaVu Sans Mono)
    python eval/vision_eval.py --out eval/vision_results_v15.json

Scores: text reading = character error rate (CER) against the text drawn into the image (spaces ignored);
questions = expected answer found in the reply; seconds per image (model already loaded); load time; peak RSS.
The images contain no personal data; they are drawn by this script (MIT, like the code).
"""
from __future__ import annotations

import argparse
import json
import resource
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
DIR = ROOT / 'eval' / 'vision'
FONTS = '/usr/share/fonts/opentype/tlwg/'

# id, lines of text drawn (for OCR cases), background, question, expected (any of)
TEXT_CASES = [
    ('th-sign', ['ร้านกาแฟบ้านสวน', 'เปิดทุกวัน 8:00 - 17:00'], 'white', 'Loma-Bold.otf', 44),
    ('th-menu', ['เมนูวันนี้', 'ข้าวผัดกุ้ง 60 บาท', 'ต้มยำทะเล 120 บาท', 'ชาเย็น 35 บาท'], '#fff6d5', 'Loma.otf', 36),
    ('th-notice', ['ประกาศ', 'ห้องสมุดปิดปรับปรุง', 'วันที่ 5 พฤศจิกายน'], '#dff0ff', 'Loma-BoldOblique.otf', 40),
    ('th-small', ['กรุณาถอดรองเท้าก่อนเข้าห้อง', 'ขอบคุณค่ะ'], 'white', 'Loma.otf', 24),
    ('th-dark', ['สถานีรถไฟเพชรบุรี', 'ชานชาลา 2'], '#1e2b3a', 'Loma-Bold.otf', 42),
    ('en-sign', ['OPEN 24 HOURS', 'No parking in front of the gate'], 'white', 'Loma-Bold.otf', 38),
    ('en-receipt', ['RECEIPT #0427', 'Coffee x2   90.00', 'Cake x1     65.00', 'TOTAL      155.00'], '#f4f4f4', '/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf', 30),
    ('mixed', ['TER-AI อ่านภาพได้แล้ว', 'version 0.15.0'], 'white', 'Loma-Bold.otf', 38),
]
QA_CASES = [
    ('shapes-1', 'ในภาพมีวงกลมกี่วง ตอบเป็นตัวเลข', ['3', 'สาม']),
    ('shapes-2', 'สี่เหลี่ยมในภาพสีอะไร', ['เขียว']),
    ('chart', 'แท่งไหนสูงที่สุด ตอบชื่อเดือน', ['มีนา']),
    ('scene', 'ภาพนี้เป็นกลางวันหรือกลางคืน', ['กลางวัน']),
    ('menu-q', 'ต้มยำทะเลราคาเท่าไร', ['120']),
    ('receipt-q', 'What is the total on this receipt?', ['155']),
]
OCR_Q = 'อ่านข้อความทั้งหมดในภาพนี้ คัดลอกตามที่เขียน บรรทัดละบรรทัด ไม่ต้องอธิบาย'


def make() -> None:
    from PIL import Image, ImageDraw, ImageFont
    DIR.mkdir(parents=True, exist_ok=True)
    for cid, lines, bg, font, size in TEXT_CASES:
        f = ImageFont.truetype(font if font.startswith('/') else FONTS + font, size)
        im = Image.new('RGB', (760, 90 + len(lines) * int(size * 1.7)), bg)
        d = ImageDraw.Draw(im)
        fg = 'white' if bg.startswith('#1') else 'black'
        for i, ln in enumerate(lines):
            d.text((40, 40 + i * int(size * 1.7)), ln, font=f, fill=fg)
        im.save(DIR / f'{cid}.png', optimize=True)
    im = Image.new('RGB', (640, 400), 'white')
    d = ImageDraw.Draw(im)
    for x in (60, 250, 440):
        d.ellipse([x, 60, x + 130, 190], fill='#d62828')
    d.rectangle([220, 250, 420, 360], fill='#2a9d8f')
    im.save(DIR / 'shapes-1.png', optimize=True)
    im.save(DIR / 'shapes-2.png', optimize=True)
    im = Image.new('RGB', (640, 420), 'white')
    d = ImageDraw.Draw(im)
    f = ImageFont.truetype(FONTS + 'Loma-Bold.otf', 26)
    for i, (m, h) in enumerate([('ม.ค.', 120), ('ก.พ.', 180), ('มี.ค.', 300), ('เม.ย.', 210)]):
        x = 70 + i * 140
        d.rectangle([x, 360 - h, x + 80, 360], fill='#457b9d')
        d.text((x + 10, 368), m, font=f, fill='black')
    im.save(DIR / 'chart.png', optimize=True)
    im = Image.new('RGB', (640, 400), '#8ecae6')
    d = ImageDraw.Draw(im)
    d.ellipse([480, 40, 580, 140], fill='#ffb703')
    d.rectangle([0, 300, 640, 400], fill='#3a7d44')
    d.polygon([(120, 300), (200, 200), (280, 300)], fill='#6b4f3a')
    im.save(DIR / 'scene.png', optimize=True)


def cer(ref: str, hyp: str) -> float:
    r, h = ''.join(ref.split()), ''.join(hyp.split())
    prev = list(range(len(h) + 1))
    for i, a in enumerate(r, 1):
        cur = [i]
        for j, b in enumerate(h, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (a != b)))
        prev = cur
    return prev[-1] / max(1, len(r))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--make', action='store_true')
    ap.add_argument('--model', default=None)
    ap.add_argument('--out', default=None)
    a = ap.parse_args(argv)
    if a.make:
        make()
        print('wrote', DIR)
        return 0
    from terai_router.brain.local import LocalLM
    from terai_router.brain.cli import VISION_SYSTEM
    lm = LocalLM(model=a.model, vision=True, auto_download=False)
    lm.load()
    rows = []
    for cid, lines, *_ in TEXT_CASES:
        t = time.time()
        out = lm.look(str(DIR / f'{cid}.png'), OCR_Q, system=VISION_SYSTEM)
        ref = '\n'.join(lines)
        rows.append({'id': cid, 'kind': 'ocr', 'ref': ref, 'answer': out, 'cer': round(cer(ref, out), 4),
                     'seconds': round(time.time() - t, 2)})
        print(cid, rows[-1]['cer'], rows[-1]['seconds'], out.replace('\n', ' / ')[:120], file=sys.stderr)
    for cid, q, exp in QA_CASES:
        img = {'menu-q': 'th-menu', 'receipt-q': 'en-receipt'}.get(cid, cid)
        t = time.time()
        out = lm.look(str(DIR / f'{img}.png'), q, system=VISION_SYSTEM, max_tokens=120)
        ok = any(e in out.replace(',', '') for e in exp)
        rows.append({'id': cid, 'kind': 'qa', 'question': q, 'answer': out, 'ok': ok,
                     'seconds': round(time.time() - t, 2)})
        print(cid, ok, rows[-1]['seconds'], out.replace('\n', ' / ')[:120], file=sys.stderr)
    ocr = [r for r in rows if r['kind'] == 'ocr']
    th = [r for r in ocr if not r['id'].startswith('en')]
    summary = {
        'model': 'TERAI1 vision (' + lm.label + ')', 'images': len(rows),
        'ocr_cer_mean': round(statistics.mean(r['cer'] for r in ocr), 4),
        'ocr_cer_thai_mean': round(statistics.mean(r['cer'] for r in th), 4),
        'ocr_exact': f"{sum(1 for r in ocr if r['cer'] == 0)}/{len(ocr)}",
        'qa_correct': f"{sum(1 for r in rows if r.get('ok'))}/{len(QA_CASES)}",
        'seconds_per_image_p50': round(statistics.median(r['seconds'] for r in rows), 2),
        'seconds_per_image_max': max(r['seconds'] for r in rows),
        'load_s': lm.load_seconds, 'threads': lm.threads,
        'peak_rss_mb': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024,
    }
    print(json.dumps(summary, ensure_ascii=False))
    if a.out:
        Path(a.out).write_text(json.dumps({'summary': summary, 'rows': rows}, ensure_ascii=False, indent=1) + '\n',
                               encoding='utf-8')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
