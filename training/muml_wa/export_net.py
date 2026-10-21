"""Export the trained MuML 1.0 network to the MuML WA weight file (no torch needed to run it afterwards).

    python training/muml_wa/export_net.py --ckpt muml-1.0.pt --out muml-1.0-int8.bin

The checkpoint comes from training/muml/train.py (MuML 1.0: decoder-only transformer, 4 layers, d_model 256,
4 heads, context 512, 163 tokens, 3,332,352 parameters, trained from scratch on the Nottingham Music Database).

File layout (little endian):
    b'MUMLWA1\\0' | uint32 header length | header JSON (utf-8) | tensor data
Every 2-D weight is stored as int8 with one float32 scale per output row (symmetric, scale = max|row| / 127);
biases and LayerNorm parameters are float32. The header lists name, shape, dtype and byte offsets.
The weights are data derived from the Nottingham dataset (GPL-3.0); see DATA_LICENSE.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct

MAGIC = b'MUMLWA1\0'


def export(ckpt_path: str, out_path: str, bits: int = 8) -> dict:
    import numpy as np
    import torch
    ck = torch.load(ckpt_path, map_location='cpu', weights_only=False)
    sd = ck['model']
    tensors, blobs, off = [], [], 0
    qmax = (1 << (bits - 1)) - 1
    for name, t in sd.items():
        if name == 'head.weight':  # tied to tok.weight
            continue
        a = t.detach().float().numpy()
        if a.ndim == 2:
            scale = np.abs(a).max(axis=1) / qmax
            scale[scale == 0] = 1.0
            q = np.clip(np.rint(a / scale[:, None]), -qmax, qmax).astype(np.int8)
            parts = [('q', q.tobytes(), 'int8'), ('scale', scale.astype('<f4').tobytes(), 'float32')]
        else:
            parts = [('data', a.astype('<f4').tobytes(), 'float32')]
        ent = {'name': name, 'shape': list(a.shape)}
        for key, b, dt in parts:
            pad = (-off) % 4
            if pad:
                blobs.append(b'\0' * pad)
                off += pad
            ent[key] = {'offset': off, 'bytes': len(b), 'dtype': dt}
            blobs.append(b)
            off += len(b)
        tensors.append(ent)
    header = {'format': 'muml-wa-net-1', 'model': 'MuML 1.0', 'quant': f'int{bits} per-row symmetric',
              'config': ck['config'], 'vocab': ck['vocab'], 'epoch': ck.get('epoch'),
              'val_loss': ck.get('val_loss'), 'tied_head': True, 'tensors': tensors,
              'license': 'GPL-3.0 (data derived from the Nottingham Music Database, see DATA_LICENSE)'}
    hb = json.dumps(header, separators=(',', ':')).encode('utf-8')
    hb += b' ' * ((-(len(MAGIC) + 4 + len(hb))) % 4)
    data = MAGIC + struct.pack('<I', len(hb)) + hb + b''.join(blobs)
    with open(out_path, 'wb') as f:
        f.write(data)
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(), 'tensors': len(tensors)}


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--ckpt', required=True)
    ap.add_argument('--out', required=True)
    a = ap.parse_args()
    print(json.dumps(export(a.ckpt, a.out)))
