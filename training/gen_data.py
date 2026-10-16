#!/usr/bin/env python3
"""Build the v0.7 training set -> training/train_v07.json

Sources (none of them is eval/test_set.json or eval/heldout_v07.json):
  1. template phrasings written for v0.7 (TEMPLATES below), with slots for numbers and names
  2. v0.5 / v0.6 clean training sentences and Bogus's real labeled training sentences (v0.6.1 split)
  3. typo augmentation: Bogus's typing-profile pairs applied in reverse (correct -> typed) plus
     generic Thai typing patterns (tone mark drop/swap, same-sound consonants, vowel length,
     silent letters, dropped sara e, r/l swap)
Guard: any sample whose normalized+folded text equals a test or held-out text is dropped.
"""
import json
import os
import random
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, 'src'))
from terai_router.normalizer import fold, normalize, _load  # noqa: E402

V061 = '/root/work/terminal-ai/v0.6.1'
NAMES = ['บอส', 'แนน', 'โอม', 'มายา', 'บิ๊ก', 'เจมส์', 'ฟ้า', 'มิ้นท์', 'แบงค์', 'เก่ง', 'ปอนด์', 'ไอซ์', 'บีม', 'นุ่น',
         'ตาล', 'ป๊อป', 'แม็ก', 'โจ้', 'เอ็ม', 'ณัฐ', 'ภูมิ', 'พลอย', 'กาต์ตูน', 'น้ำ', 'ปลา', 'หมี', 'เฟิร์ส',
         'john', 'alex', 'sara', 'ken', 'nina', 'Leo', 'Kai', 'Bo', 'klasster', 'neo']

T = {
 'calc': ['{a}+{b}', '{a} บวก {b}', '{a} ลบ {b}', '{a} คูณ {b}', '{a} หาร {b}', '{a}x{b}', '{a}*{b}', '{a}/{b}', '{a}-{b}',
          'บวกเลข {a}+{b}', 'บวกเลข', 'ลบเลข', 'คูณเลข', 'หารเลข', 'หาผลรวม {a}+{b}+{c}', 'หาผลรวม', 'ผลรวมของ {a} กับ {b}',
          'ผลคูณ {a} กับ {b}', 'ผลต่าง {a} กับ {b}', '{a} ยกกำลัง {b}', 'รากที่สอง {a}', '{a} เปอร์เซ็นต์ของ {b}', 'คิดเลข',
          'คำนวณ {a}+{b}', 'คำนวณ', 'เลขนี้เท่าไร {a}*{b}', '{a}+{b} ได้เท่าไร', '{a}+{b} เท่ากับเท่าไหร่',
          '{a} คูณ {b} ได้เท่าไร', '{a}คูณ{b}ได้เท่าไร', 'หาค่า {a}/{b}', 'ช่วยหาร {a} ด้วย {b}', '{a} ลบด้วย {b}', 'เอา {a} บวก {b}',
          'เอา {a} คูณ {b}', '{a} กับ {b} รวมกันได้เท่าไร', 'คิดเลขในใจ', 'ทำเลข', 'เครื่องคิดเลข', 'โจทย์เลข {a}+{b}',
          'เท่ากับเท่าไร {a}-{b}', 'ได้เท่าไร', '{a} หาร {b} เหลือเศษเท่าไร', 'หาค่าเฉลี่ย {a} {b} {c}',
          'what is {a} plus {b}', 'what is {a} minus {b}', 'calculate {a}*{b}', 'compute {a}/{b}', '{a} times {b}',
          'sum of {a} and {b}', 'calc {a}+{b}', 'math', 'do the math'],
 'forget': ['รีเซ็ต', 'ล้างความจำ', 'ลบความจำ', 'ลืมชื่อผม', 'ลืมชื่อฉัน', 'ลืมทุกอย่าง', 'ลืมให้หมด', 'ลบข้อมูลทั้งหมด',
            'ลบข้อมูลผม', 'ล้างข้อมูล', 'ล้างหน่วยความจำ', 'เริ่มใหม่หมด', 'เริ่มใหม่ตั้งแต่ต้น', 'รีเซ็ตความจำ',
            'รีเซ็ตทั้งหมด', 'ลบที่จำไว้', 'ลืมสิ่งที่ผมบอก', 'ลบประวัติ', 'ล้างประวัติ', 'ล้าง memory', 'ลบ memory',
            'ไม่ต้องจำชื่อผมแล้ว', 'ลืมฉันซะ', 'ฟอร์แมตความจำ', 'ลบชื่อผมออก', 'reset', 'reset memory', 'clear memory',
            'forget me', 'forget everything', 'wipe memory', 'clear all data', 'delete memory'],
 'get_name': ['ผมชื่ออะไร', 'ฉันชื่ออะไร', 'เราชื่ออะไร', 'หนูชื่ออะไร', 'ชื่อผมคืออะไร', 'ชื่อฉันคืออะไร', 'บอกชื่อผมหน่อย',
              'จำชื่อผมได้ไหม', 'จำได้ไหมว่าผมชื่ออะไร', 'รู้จักชื่อผมไหม', 'ผมคือใคร', 'ฉันคือใคร', 'รู้ไหมผมชื่ออะไร',
              'คุณจำชื่อผมได้ป่าว', 'ผมชื่อไร', 'เมื่อกี้ผมบอกชื่อว่าอะไร', 'ชื่อที่คุณเรียกผมคืออะไร',
              'จำได้ป่าวว่าฉันชื่ออะไร', 'เรียกผมว่าอะไร', 'ผมชื่ออะไรนะ', "what's my name", 'who am i',
              'do you know my name', 'tell me my name', 'say my name'],
 'greet': ['สวัสดี', 'หวัดดี', 'ดี', 'ดีจ้า', 'ดีครับ', 'ดีค่ะ', 'ว่าไง', 'เป็นไงบ้าง', 'สบายดีไหม', 'อรุณสวัสดิ์', 'สวัสดีตอนบ่าย',
           'ทักทายหน่อย', 'เฮ้', 'เฮ้ย', 'หวัดดีจ้า', 'ดีจ้า AI', 'สวัสดีตอนเย็น', 'ไง', 'ไงบ้าง', 'หวัดดีเพื่อน', 'มอร์นิ่ง',
           'สวัสดีบอท', 'เป็นยังไงบ้าง', 'สบายดีป่าว', 'hello', 'hi', 'hey', 'good morning', 'good evening', 'yo', 'sup'],
 'help': ['ช่วยด้วย', 'ใช้ยังไง', 'ใช้งานยังไง', 'วิธีใช้', 'บอกวิธีใช้', 'คู่มือ', 'มีคำสั่งอะไรบ้าง', 'คำสั่งทั้งหมด', 'ดูคำสั่ง',
          'รายการคำสั่ง', 'ทำอะไรได้บ้าง', 'ทำอะไรเป็นบ้าง', 'มีฟีเจอร์อะไร', 'เมนู', 'ขอดูเมนู', 'ใช้คำสั่งอะไรได้บ้าง',
          'สอนใช้หน่อย', 'เริ่มใช้ยังไง', 'พิมพ์อะไรได้บ้าง', 'คำสั่งมีอะไร', 'ช่วยอะไรได้บ้าง', 'ไม่รู้จะใช้ยังไง',
          'help', 'commands', 'show commands', 'what can you do', 'how to use', 'menu', 'usage help', '?'],
 'random': ['สุ่มเลข', 'สุ่มตัวเลข', 'สุ่ม {a} ถึง {b}', 'สุ่มเลข {a}-{b}', 'สุ่มให้หน่อย', 'ขอเลขสุ่ม', 'เลือกเลขให้หน่อย', 'ออกเลขอะไร',
            'ทอยลูกเต๋า', 'ทอยเหรียญ', 'สุ่มหน่อย', 'สุ่มเลขระหว่าง {a} กับ {b}', 'เลขนำโชค', 'ขอตัวเลขสุ่ม', 'สุ่มมาหนึ่งเลข',
            'เลือกสุ่ม', 'สุ่มเลขไม่เกิน {a}', 'สุ่มเลข {a} หลัก', 'สุ่มค่า', 'เสี่ยงทาย', 'สุ่มเลขเดียว',
            'random', 'random number', 'roll a dice', 'roll dice', 'flip a coin', 'pick a number', 'rand {a} {b}'],
 'set_name': ['ผมชื่อ{n}', 'ฉันชื่อ{n}', 'หนูชื่อ{n}', 'เราชื่อ{n}', 'เรียกผมว่า{n}', 'เรียกฉันว่า{n}', 'เปลี่ยนชื่อผมเป็น{n}',
              'ชื่อผมคือ{n}', 'ชื่อฉันคือ{n}', 'ตั้งชื่อผมว่า{n}', 'จำไว้นะผมชื่อ{n}', 'ชื่อของผมคือ{n}', 'ผมชื่อเล่น{n}',
              'ต่อไปเรียกผมว่า{n}', 'เรียกผมว่า{n}ก็ได้', 'ผมชื่อ{n}นะ', 'นี่{n}เอง', 'ผมคือ{n}', 'จำชื่อผมไว้ {n}',
              'บันทึกชื่อผมว่า{n}', 'เปลี่ยนชื่อเป็น{n}', 'my name is {n}', 'call me {n}', "i'm {n}", 'set name {n}', 'name {n}'],
 'stats': ['สถิติ', 'ดูสถิติ', 'สถิติการใช้งาน', 'ข้อมูลการใช้งาน', 'นับข้อความ', 'คุยกันมากี่ข้อความแล้ว',
           'คุยกันนานแค่ไหนแล้ว', 'ใช้ไปเท่าไรแล้ว', 'คุยไปกี่ครั้งแล้ว', 'พิมพ์ไปกี่ข้อความ', 'จำนวนข้อความ', 'ยอดการใช้งาน',
           'คุยกันกี่นาทีแล้ว', 'เปิดมานานเท่าไรแล้ว', 'สรุปการใช้งาน', 'นับจำนวนที่คุย', 'สถิติแชท', 'คุยไปเยอะแค่ไหน',
           'ใช้งานมานานเท่าไหร่', 'ข้อความทั้งหมดกี่อัน', 'usage', 'stats', 'statistics', 'message count', 'how long have we talked',
           'session stats'],
 'thanks': ['ขอบคุณ', 'ขอบใจ', 'ขอบคุณมาก', 'ขอบใจนะ', 'โอเค ขอบคุณ', 'เยี่ยม', 'เยี่ยมมาก', 'ดีมาก', 'เก่งมาก', 'ขอบคุณที่ช่วย',
            'ขอบคุณสำหรับคำตอบ', 'ซึ้งใจ', 'ขอบพระคุณ', 'สุดยอด ขอบคุณ', 'เจ๋ง ขอบใจ', 'ความจริงดีมาก ขอบคุณ',
            'ขอบคุณนะที่ทำให้', 'thanks', 'thank you', 'thx', 'ty', 'thanks a lot', 'great thanks', 'nice'],
 'time': ['กี่โมง', 'กี่โมงแล้ว', 'ตอนนี้กี่โมง', 'ตอนนี้เวลาเท่าไร', 'บอกเวลา', 'ขอดูเวลา', 'เวลาตอนนี้', 'วันนี้วันอะไร',
          'วันนี้วันที่เท่าไหร่', 'วันที่เท่าไร', 'วันที่วันนี้', 'เดือนอะไร', 'ปีอะไร', 'ปีนี้ปีอะไร', 'เช้าหรือยัง', 'ดึกแล้วยัง',
          'ตอนนี้เวลาอะไร', 'ดูนาฬิกา', 'พรุ่งนี้วันอะไร', 'เวลาไทยตอนนี้', 'บอกวันที่', 'ปฏิทินวันนี้', 'กี่ทุ่มแล้ว',
          'what time is it', 'time', 'date', 'today date', 'what is the date', 'what day is it', 'clock'],
 'who': ['คุณเป็นใคร', 'คุณชื่ออะไร', 'นายเป็นใคร', 'แกชื่ออะไร', 'บอทชื่ออะไร', 'แนะนำตัวหน่อย', 'ใครสร้างคุณ', 'ใครทำคุณ',
         'เป็น AI ไหม', 'เป็นคนหรือบอท', 'คุณคืออะไร', 'คุณคือใคร', 'บอกหน่อยว่าคุณเป็นใคร', 'ใครเป็นคนสร้าง', 'คุณมาจากไหน',
         'ใช้โมเดลอะไร', 'คุณทำงานยังไง', 'นายชื่ออะไร', 'บอทตัวนี้คืออะไร', 'เธอเป็นใคร', 'คุณเป็นหุ่นยนต์ไหม',
         'who are you', 'what are you', 'your name', 'who made you', 'are you ai', 'about you', 'introduce yourself'],
 'fix': ['แก้', 'แก้ใหม่', 'แก้หน่อย', 'แก้ให้หน่อย', 'ผิด', 'ผิดแล้ว', 'ผิดอีกแล้ว', 'ตอบผิด', 'พิมพ์ผิด', 'พิมพ์ผิดนะ', 'พิมพ์ผิดแก้ใหม่',
         'ไม่ถูก แก้ใหม่', 'ไม่ถูก', 'เอาใหม่', 'ทำใหม่', 'ทำใหม่หมด', 'ย้อนกลับ', 'แก้คำตอบ', 'แก้เดี๋ยวนี้', 'แก้ชื่อ',
         'อันเมื่อกี้ผิด', 'เอาอันเมื่อกี้ออก', 'แก้ skill', 'แก้ skill เลย', 'แก้ไฟล์', 'แก้โค้ด', 'แก้คำผิด', 'ผิดตรงนี้ แก้',
         'แก้ใหม่เดี๋ยวนี้', 'คำตอบผิด', 'ไม่ใช่อันนี้ แก้ใหม่', 'คำผิด', 'สะกดผิด', 'ผิดหมดเลย', 'แก้ตามนี้',
         'แก้บรรทัดนี้', 'undo', 'fix it', 'wrong', 'redo', 'that is wrong', 'typo', 'fix'],
 'go_on': ['ทำ', 'ทำเลย', 'ทำต่อ', 'ทำต่อเลย', 'ต่อ', 'ต่อเลย', 'ไปต่อ', 'เอาเลย', 'จัดไป', 'ลุย', 'ลุยเลย', 'เริ่มเลย', 'เริ่มงาน',
           'เริ่มทำ', 'ทำอีก', 'อีกรอบ', 'ขออีก', 'เอาอีก', 'ได้', 'ได้เลย', 'ตกลง', 'ตกลงทำเลย', 'โอเคทำเลย', 'โอเค', 'ใช้ได้เลย',
           'ทำเลยไม่ต้องถาม', 'ทำทุกอันเลย', 'ทำทั้งหมด', 'เอาอันนั้นแหละ ทำเลย', 'งั้นทำต่อเลย', 'ก็ทำสิ', 'สร้างเลย',
           'กดให้ด้วย', 'ส่งเลย', 'รันเลย', 'ทำต่อจนเสร็จ', 'ทำต่อได้', 'เอาอันนี้', 'เลือกอันแรก', 'ทางแรก', 'ทั้งสองอัน',
           'ใช่ ทำเลย', 'ขั้นต่อไป', 'เดินหน้า', 'ทำทุกข้อ', 'ไปเลย', 'อนุมัติ', 'เห็นด้วย ทำเลย', 'เริ่มทดสอบเลย',
           'go', 'continue', 'next', 'next step', 'next steps', 'ok go', 'yes do it', 'do it', 'proceed', 'all ideas', 'run it', 'ok'],
 'refuse': ['ไม่', 'ไม่เอา', 'ไม่ทำ', 'ไม่ต้อง', 'ไม่ต้องทำ', 'ไม่ต้องทำต่อ', 'ไม่ตอบ', 'ไม่ใช่', 'ไม่สน', 'ยกเลิก', 'ยกเลิกเลย',
            'หยุด', 'หยุดก่อน', 'หยุดทำ', 'พอแล้ว', 'พอ', 'เลิกทำ', 'ไม่ทำแล้ว', 'อันนี้ไม่เอา', 'ไม่เอาแบบนั้น', 'ไม่เอาดีกว่า',
            'ผมไม่ทำนะ', 'ปฏิเสธ', 'อย่าทำ', 'อย่าสร้าง', 'อย่าเพิ่ง', 'ไม่ต้องแก้', 'ไม่ต้องส่ง', 'ไม่อยากได้', 'ไม่สนใจ',
            'ต้องเรียงเอง ไม่เอา', 'พอก่อน', 'ไม่ใช่แบบนั้น', 'อย่าทำเด็ดขาด', 'ห้ามทำ', 'ปล่อยไว้ก่อน', 'ไม่ต้องหรอก',
            'no', 'nope', 'cancel', 'stop', 'abort', 'never mind', "don't", 'skip'],
 'status': ['สถานะ', 'ดูสถานะ', 'สถานะตอนนี้', 'ถึงไหนแล้ว', 'ไปถึงไหนแล้ว', 'เสร็จยัง', 'เสร็จหรือยัง', 'งานเสร็จยัง',
            'งานค้างมีอะไร', 'มีงานค้างไหม', 'มีอะไรค้างอยู่', 'เหลืออะไรอีก', 'ตอนนี้ทำอะไรอยู่', 'คืบหน้าเท่าไร',
            'เมื่อกี้ทำอะไรไป', 'ล่าสุดทำอะไร', 'ดู log', 'ดูบันทึก', 'ดูการบันทึก', 'ขอดูบันทึก', 'มีอะไรให้คุณทำอีก',
            'ทำไปถึงไหน', 'งานไปถึงไหน', 'ความคืบหน้า', 'รายงานความคืบหน้า', 'เหลือกี่งาน', 'ทำเสร็จกี่อันแล้ว',
            'งานที่สั่งเสร็จยัง', 'ตอนนี้อยู่ขั้นไหน', 'สรุปงานที่ทำ', 'เช็กสถานะ', 'status', 'progress', 'show log', 'done yet',
            'what are you doing', 'any pending tasks'],
}

PRE = {'*': ['', '', '', 'AI ', 'ai ', 'เอ่อ ', 'นี่ ', 'คุณ'],
       'calc': ['', 'ช่วย', 'ขอ', 'ช่วยหน่อย ', 'AI '],
       'set_name': ['', '', 'สวัสดี ', 'คือ ', 'AI '],
       'go_on': ['', '', 'งั้น', 'โอเค ', 'ก็', 'ได้ '], 'refuse': ['', '', 'ไม่ ', 'เอ่อ ', 'งั้น']}
SUF = {'*': ['', '', '', 'ครับ', 'ค่ะ', 'คะ', 'คับ', 'นะ', 'หน่อย', 'ที', 'จ้า', ' ?', 'เลย', 'ด้วย', 'หรอ', ' หน่อยสิ'],
       'calc': ['', '', 'ให้หน่อย', 'ได้เท่าไร', ' เท่ากับ', ' เท่าไหร่', '=?', 'ครับ', 'ที'],
       'set_name': ['', '', 'ครับ', 'นะ', 'ค่ะ', ' จำไว้ด้วย'],
       'greet': ['', '', 'ครับ', 'ค่ะ', 'จ้า', ' AI', 'คับ', 'นะ'],
       'thanks': ['', '', 'ครับ', 'ค่ะ', 'นะ', 'มาก', 'จ้า', 'คับ', 'มากๆ']}


def fill(tpl, rng):
    a, b, c = rng.randint(1, 99), rng.randint(1, 50), rng.randint(1, 20)
    return tpl.replace('{a}', str(a)).replace('{b}', str(b)).replace('{c}', str(c)).replace('{n}', rng.choice(NAMES))


def clean_samples(rng, per_intent=700):
    out = []
    for intent, tpls in T.items():
        pre, suf = PRE.get(intent, PRE['*']), SUF.get(intent, SUF['*'])
        seen = set()
        for t in tpls:  # every template at least once, bare
            s = fill(t, rng)
            seen.add(s)
        tries = 0
        while len(seen) < per_intent and tries < per_intent * 20:
            tries += 1
            t = fill(rng.choice(tpls), rng)
            if re.fullmatch(r"[A-Za-z0-9 ?'*/+\-=]+", t):
                s = rng.choice(['', '', 'pls ', 'hey ']) + t + rng.choice(['', '', ' please', ' pls', '?'])
            else:
                p, x = rng.choice(pre), rng.choice(suf)
                s = p + t + x
                if rng.random() < 0.25:
                    s = s.replace(' ', '')
            seen.add(s.strip())
        out += [(s, intent, 'template') for s in sorted(seen)]
    return out


P_CONS = [('ภ', 'พ'), ('ฝ', 'ผ'), ('ฝ', 'ฟ'), ('ฐ', 'ถ'), ('ณ', 'น'), ('ญ', 'ย'), ('ข', 'ค'), ('ค', 'ข'), ('ศ', 'ส'), ('ษ', 'ส'),
          ('ท', 'ถ'), ('ถ', 'ท'), ('ซ', 'ส'), ('ส', 'ซ'), ('พ', 'ภ'), ('ร', 'ล'), ('ล', 'ร'), ('จ', 'ด'), ('ด', 'ต')]
P_VOWEL = [('ไ', 'ใ'), ('ใ', 'ไ'), ('ิ', 'ี'), ('ี', 'ิ'), ('ุ', 'ู'), ('ู', 'ุ'), ('ึ', 'ื'), ('ื', 'ึ'), ('ั', '')]
P_SILENT = [('์', ''), ('หน', 'น'), ('หม', 'ม'), ('หล', 'ล'), ('หว', 'ว'), ('หย', 'ย'), ('ร็จ', '็ด'), ('เป็', 'ป็')]
TONES = '่้'


def pattern_typo(s, rng):
    """One random Thai typing error."""
    ops = ['cons', 'vowel', 'silent', 'tone_drop', 'tone_swap', 'tone_add', 'e_drop', 'dup', 'del']
    for _ in range(6):
        op = rng.choice(ops)
        if op in ('cons', 'vowel', 'silent'):
            table = {'cons': P_CONS, 'vowel': P_VOWEL, 'silent': P_SILENT}[op]
            cand = [(a, b) for a, b in table if a in s]
            if cand:
                a, b = rng.choice(cand)
                idx = [m.start() for m in re.finditer(re.escape(a), s)]
                i = rng.choice(idx)
                return s[:i] + b + s[i + len(a):]
        elif op == 'tone_drop':
            idx = [i for i, ch in enumerate(s) if ch in TONES]
            if idx:
                i = rng.choice(idx)
                return s[:i] + s[i + 1:]
        elif op == 'tone_swap':
            idx = [i for i, ch in enumerate(s) if ch in TONES]
            if idx:
                i = rng.choice(idx)
                return s[:i] + ('้' if s[i] == '่' else '่') + s[i + 1:]
        elif op == 'tone_add':
            idx = [i for i, ch in enumerate(s) if 'ก' <= ch <= 'ฮ' and (i + 1 == len(s) or s[i + 1] not in TONES + 'ิีึืุูั็')]
            if idx:
                i = rng.choice(idx)
                return s[:i + 1] + rng.choice(TONES) + s[i + 1:]
        elif op == 'e_drop':
            idx = [i for i, ch in enumerate(s) if ch == 'เ']
            if idx:
                i = rng.choice(idx)
                return s[:i] + s[i + 1:]
        elif op == 'dup' and s:
            return s + s[-1] * rng.randint(1, 4)
        elif op == 'del' and len(s) > 4:
            i = rng.randrange(len(s))
            return s[:i] + s[i + 1:]
    return s


def profile_typo(s, rng, rev):
    cand = [(typed, intended) for typed, intended in rev if intended in s]
    if not cand:
        return s
    typed, intended = rng.choice(cand)
    return s.replace(intended, typed, 1)


def main():
    rng = random.Random(7)
    d = _load()['raw']
    rev = [(t, i) for t, i, *_ in d['safe_pairs'] + d['ctx_only_pairs'] + d['candidate_pairs']]
    rev += [('ใด้', 'ได้'), ('คุน', 'คุณ'), ('ป็น', 'เป็น'), ('ใหน', 'ไหน'), ('ใช่', 'ใช้'), ('ถุก', 'ถูก'), ('หน้อย', 'หน่อย'),
            ('ข่ะ', 'ค่ะ'), ('ขะ', 'คะ'), ('คับ', 'ครับ'), ('เท่าไหล่', 'เท่าไหร่'), ('สวัดดี', 'สวัสดี'), ('เลบ', 'เลย')]
    data = clean_samples(rng)
    # v0.5/v0.6 clean train side + Bogus's real train split (v0.6.1 dataset_info.json)
    info = json.load(open(os.path.join(V061, 'dataset_info.json'), encoding='utf-8'))
    for src, rows in (('v05', info['v05_train_split']), ('v06seed', info['seed_train_split']),
                      ('real', info['real_split']['train'])):
        data += [(t, y, src) for t, y in rows]
    old = json.load(open(os.path.join(V061, 'train_data.json'), encoding='utf-8'))
    data += [(t, y, 'v06train') for y, ts in old.items() for t in ts]
    data += [('ขอนะ', 'go_on', 'real_extra'), ('แก้ skill เลยและเร่อมงาน', 'fix', 'real_extra')]
    # typo augmentation, 2 profile + 2 pattern variants per Thai sample
    aug = []
    for s, y, src in data:
        if not re.search(r'[\u0E00-\u0E7F]', s):
            continue
        for _ in range(2):
            aug.append((profile_typo(s, rng, rev), y, 'aug_profile'))
            t = pattern_typo(s, rng)
            if rng.random() < 0.3:
                t = pattern_typo(t, rng)
            aug.append((t, y, 'aug_pattern'))
    data += aug
    # guard against eval leakage
    ev = json.load(open(os.path.join(REPO, 'eval/test_set.json'), encoding='utf-8'))
    ho = json.load(open(os.path.join(REPO, 'eval/heldout_v07.json'), encoding='utf-8'))
    keys = set()
    for sets in (ev, {k: v for k, v in ho.items() if not k.startswith('_')}):
        for items in sets.values():
            for t, _ in items:
                keys.add(fold(normalize(t)))
                keys.add(fold(t))
    uniq, dropped = {}, 0
    for s, y, src in data:
        k = fold(normalize(s))
        if not k or k in keys or fold(s) in keys:
            dropped += 1
            continue
        uniq.setdefault((s, y), src)
    rows = [[s, y, src] for (s, y), src in uniq.items()]
    rng.shuffle(rows)
    json.dump({'n': len(rows), 'dropped_by_eval_guard_or_empty': dropped, 'rows': rows},
              open(os.path.join(HERE, 'train_v07.json'), 'w', encoding='utf-8'), ensure_ascii=False)
    from collections import Counter
    print('train rows', len(rows), 'dropped', dropped, Counter(y for _, y, _ in rows).most_common())


if __name__ == '__main__':
    main()
