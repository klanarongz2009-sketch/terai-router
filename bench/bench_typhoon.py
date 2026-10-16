#!/usr/bin/env python3
"""Zero-shot intent classification with Typhoon 2 1B instruct (typhoon-ai/llama3.2-typhoon2-1b-instruct)
on the same frozen test set and held-out set as TER-AI. CPU only, fp32, greedy decoding.

Output: bench/typhoon_results.json (per-item prediction + latency) and a summary line.
"""
import json
import os
import platform
import sys
import time

import torch
import transformers
from transformers import AutoModelForCausalLM, AutoTokenizer

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MODEL_ID = 'typhoon-ai/llama3.2-typhoon2-1b-instruct'

INTENTS = {
    'greet': 'ทักทาย เช่น สวัสดี หวัดดี hello',
    'help': 'ถามวิธีใช้ ขอดูคำสั่งหรือเมนู',
    'time': 'ถามเวลา วันที่ วัน เดือน ปี',
    'get_name': 'ถามว่าผู้ใช้ชื่ออะไร (ชื่อของผู้ใช้เอง)',
    'set_name': 'บอกชื่อตัวเองให้จำ หรือให้เปลี่ยนชื่อที่ใช้เรียก',
    'calc': 'ให้คิดเลข คำนวณ บวก ลบ คูณ หาร',
    'random': 'ให้สุ่มเลขหรือสุ่มเลือก',
    'stats': 'ถามสถิติการคุย จำนวนข้อความ คุยกันนานแค่ไหน',
    'forget': 'ให้ลบความจำ รีเซ็ต ลืมข้อมูล',
    'who': 'ถามว่าบอทเป็นใคร ชื่ออะไร ใครสร้าง',
    'thanks': 'ขอบคุณ ชม',
    'fix': 'บอกว่าผิด ให้แก้ ทำใหม่ ย้อนกลับ',
    'go_on': 'สั่งให้ทำต่อ เริ่มทำ ตกลง ทำเลย',
    'refuse': 'ปฏิเสธ ไม่เอา ยกเลิก หยุด',
    'status': 'ถามความคืบหน้า สถานะงาน เสร็จหรือยัง ดู log',
}

SYSTEM = ('You are an intent classifier for a Thai chatbot. The user text may contain Thai typos. '
          'Choose exactly one label from this list and reply with the label only, nothing else.\n' +
          '\n'.join(f'{k}: {v}' for k, v in INTENTS.items()))


def parse(out):
    o = out.strip().lower()
    hits = [(o.find(k), k) for k in INTENTS if k in o]
    return min(hits)[1] if hits else None


def main():
    torch.set_num_threads(os.cpu_count())
    t0 = time.time()
    tok = AutoTokenizer.from_pretrained(MODEL_ID)
    model = AutoModelForCausalLM.from_pretrained(MODEL_ID, dtype=torch.float32)
    model.eval()
    load_s = time.time() - t0
    test = json.load(open(os.path.join(ROOT, 'eval/test_set.json'), encoding='utf-8'))
    held = json.load(open(os.path.join(ROOT, 'eval/heldout_v07.json'), encoding='utf-8'))
    sets = {'test': test, 'heldout': {k: v for k, v in held.items() if not k.startswith('_')}}

    def classify(text):
        msgs = [{'role': 'system', 'content': SYSTEM}, {'role': 'user', 'content': text}]
        ids = tok.apply_chat_template(msgs, add_generation_prompt=True, return_tensors='pt', return_dict=True)
        t = time.perf_counter()
        with torch.no_grad():
            g = model.generate(**ids, max_new_tokens=6, do_sample=False, pad_token_id=tok.eos_token_id)
        dt = time.perf_counter() - t
        out = tok.decode(g[0][ids['input_ids'].shape[1]:], skip_special_tokens=True)
        return out, dt

    for w in ('สวัสดี', 'ทำต่อ', 'กี่โมง'):
        classify(w)  # warm-up, not timed
    res = {}
    for sname, subsets in sets.items():
        rows = []
        for sub, items in subsets.items():
            for text, gold in items:
                out, dt = classify(text)
                rows.append({'subset': sub, 'text': text, 'gold': gold, 'raw': out, 'pred': parse(out), 'sec': round(dt, 4)})
        ok = sum(r['pred'] == r['gold'] for r in rows)
        lat = sorted(r['sec'] for r in rows)
        res[sname] = {'n': len(rows), 'correct': ok, 'acc': round(ok / len(rows), 4),
                      'unparsed': sum(r['pred'] is None for r in rows),
                      'latency_ms_mean': round(1000 * sum(lat) / len(lat), 1),
                      'latency_ms_p50': round(1000 * lat[len(lat) // 2], 1), 'rows': rows}
        print(sname, ok, '/', len(rows), res[sname]['latency_ms_mean'], 'ms', flush=True)
        json.dump({'results': res}, open(os.path.join(HERE, 'typhoon_results.partial.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    snap = os.path.join(os.path.expanduser('~/.cache/huggingface/hub'), 'models--typhoon-ai--llama3.2-typhoon2-1b-instruct')
    size = sum(os.path.getsize(os.path.join(d, f)) for d, _, fs in os.walk(os.path.join(snap, 'blobs')) for f in fs)
    meta = {'model_id': MODEL_ID, 'revision': '7513a054da229b9dde7c8cd1a7da57baa36ac59b', 'dtype': 'float32',
            'params': sum(p.numel() for p in model.parameters()), 'download_bytes': size,
            'torch': torch.__version__, 'transformers': transformers.__version__, 'python': platform.python_version(),
            'threads': torch.get_num_threads(), 'cpu': platform.processor() or 'AMD EPYC (lscpu)', 'load_s': round(load_s, 1),
            'decoding': 'greedy, max_new_tokens=6, chat template, system prompt lists the 15 intents with Thai descriptions'}
    json.dump({'meta': meta, 'results': res}, open(os.path.join(HERE, 'typhoon_results.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print(json.dumps(meta, ensure_ascii=False))


if __name__ == '__main__':
    main()
