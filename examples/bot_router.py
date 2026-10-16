"""Minimal Thai bot: route each message to a handler, fall back when confidence is low.

    python examples/bot_router.py
"""
import datetime
import random
import re

from terai_router import route

state = {'name': None, 'count': 0}


def on_calc(text):
    expr = re.sub(r'[^0-9+\-*/(). ]', '', text.replace('คูณ', '*').replace('หาร', '/')
                  .replace('บวก', '+').replace('ลบ', '-').replace('x', '*'))
    try:
        return str(eval(expr, {'__builtins__': {}}, {})) if expr.strip() else 'พิมพ์โจทย์มาด้วย เช่น 12*8'
    except Exception:
        return 'คำนวณไม่ได้'


def on_set_name(text):
    m = re.search(r'(?:ชื่อ|ว่า|name is|call me)\s*(\S+)', text)
    state['name'] = m.group(1) if m else None
    return f"จำแล้ว: {state['name']}" if state['name'] else 'ไม่เจอชื่อในประโยค'


HANDLERS = {
    'greet': lambda t: 'สวัสดี',
    'time': lambda t: datetime.datetime.now().strftime('%Y-%m-%d %H:%M'),
    'calc': on_calc,
    'random': lambda t: str(random.randint(1, 100)),
    'set_name': on_set_name,
    'get_name': lambda t: state['name'] or 'ยังไม่ได้บอกชื่อ',
    'forget': lambda t: state.update(name=None) or 'ล้างความจำแล้ว',
    'stats': lambda t: f"คุยไป {state['count']} ข้อความ",
}

if __name__ == '__main__':
    for msg in ['หวัดดี', 'ผมชื่อ โบกัส', 'ผมชือ่อะไร', '12 คูณ 8 ใด้เท่าไร', 'คุยไปกี่ข้อความแล้ว']:
        state['count'] += 1
        r = route(msg)
        handler = HANDLERS.get(r['intent']) if r['confidence'] >= 0.4 else None
        reply = handler(msg) if handler else f"(intent={r['intent']}, ไม่มี handler หรือไม่มั่นใจ)"
        print(f'> {msg}\n  [{r["intent"]} {r["confidence"]:.2f}] {reply}')
