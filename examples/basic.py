"""Classify a few sentences, typos included.

    python examples/basic.py
"""
from terai_router import route

for text in ['สวัดดีครับ', 'เส็ดหรือยัง', 'ช้วยบวก 15+27 หน้อย', 'พิมพิด แก้ใหม่', 'ไม่เอาแล้ว']:
    r = route(text)
    print(f"{text:<24} -> {r['intent']:<9} {r['confidence']:.2f}  normalized: {r['normalized']}")
