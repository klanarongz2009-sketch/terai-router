"""IoT-style use: map Thai commands to device actions without any network call.

TER-AI's 15 intents are general bot intents; for a device you map the ones you need
(go_on -> confirm, refuse -> cancel, status -> report) and keep everything on-device.

    python examples/iot_switch.py
"""
from terai_router import route

ACTIONS = {'go_on': 'CONFIRM', 'refuse': 'CANCEL', 'status': 'REPORT', 'help': 'SHOW_HELP'}

for said in ['ทำเลย', 'ไม่เอาดีกว่า', 'เส็ดยัง', 'ใช่งานยังไง']:
    r = route(said)
    print(f"{said:<16} {r['intent']:<7} {r['confidence']:.2f} -> {ACTIONS.get(r['intent'], 'IGNORE')}")
