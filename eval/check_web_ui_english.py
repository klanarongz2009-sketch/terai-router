"""Check that the web demo UI (docs/) is English only.

Rules (memory M113): the GitHub Pages demo has an English-only UI. There is no
Thai page, no language switch and no Thai fallback text. Thai is allowed only
where it is functional:
  * example prompts that show the engines accept Thai (each shown with its
    English meaning, next to English examples),
  * the polite particle value passed to TTH,
  * engine code (chat.js, tth.js, sankpup.js, muml_wa.js, terai.js) and the
    remix rules in temmo/community.js, which read and write Thai text,
  * the Thai content inside a Temmo game (its story, names and spoken lines).

Run: python eval/check_web_ui_english.py   (exit 0 = clean)
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / 'docs'
THAI = re.compile('[\u0e00-\u0e7f]')

# Thai kept on purpose in demo_template.html: example prompts (functional input
# for the Thai engines) and the TTH polite particle value.
ALLOWED_TEMPLATE = [
    # Router examples
    'เส็ดหรือยัง', 'ช้วยบวก 2+3', 'ทำต่อ', 'หวัดดีคับ', 'ตอนนี้กี่โมงแล้ว', 'สุ่มเลขให้หน่อย',
    'ลืมทั้งหมด', 'ขอบคุนนะ',
    # SANKPUP examples
    'แมวสีส้มนั่งบนดวงจันทร์', 'บ้านหลังเล็กกับต้นไม้สองต้น ตอนกลางคืน', 'เรือใบสีแดงกลางทะเล', 'หุ่นยนต์ถือดอกไม้',
    # MuML examples
    'เพลงโฟล์คสนุกๆ จิ๊ก', 'เพลงร็อกมันส์ๆ 140 bpm คีย์ E minor 20 วินาที', 'เพลงเศร้า วอลทซ์ คีย์ A minor',
    # Chat examples (and the Thai example in the chat placeholder)
    'สวัสดี', 'ผมชื่อบอส', 'แล้ว 5 ล่ะ', 'ผมชื่ออะไร', 'ผมอยู่ ม.4', 'ดาวอังคารคืออะไร', 'เล่าต่อ',
    '100 กิโลเมตรเป็นกี่ไมล์', 'จำอะไรเกี่ยวกับผมได้บ้าง',
    # TTH polite particle value (engine parameter)
    "polite: 'ค่ะ'",
]

# JS that builds UI: any Thai literal on a line that writes to the page is UI text.
UI_CALL = re.compile(r"(\blog\(|innerHTML|textContent|\bbtn\(|\btext\(|placeholder|\.title\s*=|alert\(|confirm\(|prompt\()")
THAI_LITERAL = re.compile(r"(['\"`])((?:\\.|(?!\1).)*?[\u0e00-\u0e7f](?:\\.|(?!\1).)*?)\1")
UI_JS = ['temmo/temmo.js', 'temmo/community.js', 'temmo/engine.js', 'chat.js', 'tth.js',
         'sankpup.js', 'muml_wa.js', 'terai.js']


def check():
    errors = []
    # 1. No Thai page and no language switch.
    for p in DOCS.rglob('*.html'):
        rel = p.relative_to(DOCS).as_posix()
        if rel not in ('index.html', 'demo_template.html') and not rel.startswith('temmo/games/'):
            errors.append(f'{rel}: unexpected page (only index.html and Temmo games are allowed)')
        if re.search(r'(^|[._-])th\.html$', rel):
            errors.append(f'{rel}: Thai page is not allowed')
    tpl = (DOCS / 'demo_template.html').read_text(encoding='utf8')
    if '<html lang="en">' not in tpl:
        errors.append('demo_template.html: <html lang="en"> missing')
    if re.search(r'hreflang|data-lang|setLang|lang-switch|langToggle', tpl):
        errors.append('demo_template.html: language switch found')

    # 2. Template: Thai only inside the allowed example prompts.
    for i, line in enumerate(tpl.split('\n'), 1):
        rest = line
        for a in sorted(ALLOWED_TEMPLATE, key=len, reverse=True):
            rest = rest.replace(a, '')
        if THAI.search(rest):
            errors.append(f'demo_template.html:{i}: Thai UI text: {line.strip()[:120]}')

    # 3. UI JS: no Thai literal on a line that writes to the page.
    for name in UI_JS:
        for i, line in enumerate((DOCS / name).read_text(encoding='utf8').split('\n'), 1):
            if UI_CALL.search(line) and THAI_LITERAL.search(line):
                errors.append(f'{name}:{i}: Thai UI text: {line.strip()[:120]}')

    # 4. Temmo cards: English title and tagline_en for every listed game.
    idx = json.loads((DOCS / 'temmo' / 'games' / 'index.json').read_text(encoding='utf8'))
    for g in idx['games']:
        for key in ('tagline_en', 'idea_en', 'by'):
            if not g.get(key) or THAI.search(g[key]):
                errors.append(f'games/index.json {g["file"]}: {key} must be English')
        html = (DOCS / 'temmo' / 'games' / g['file']).read_text(encoding='utf8')
        m = re.search(r'"title": "([^"]*)"', html)
        if not m or THAI.search(m.group(1)):
            errors.append(f'{g["file"]}: English "title" missing')
        # the game's engine chrome (menus, HUD) is the shared English runtime
        if (DOCS / 'temmo' / 'engine.js').read_text(encoding='utf8') not in html:
            errors.append(f'{g["file"]}: embedded engine differs from docs/temmo/engine.js')
    return errors


if __name__ == '__main__':
    errs = check()
    for e in errs:
        print(e)
    print('web UI English check:', 'OK' if not errs else f'{len(errs)} problem(s)')
    sys.exit(1 if errs else 0)
