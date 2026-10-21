"""Real TTH synthesis. Skipped unless TERAI_TTH_REAL=1 (needs the tth extra; Wayu downloads ~315 MB once).

    TERAI_TTH_REAL=1 python -m pytest tests/test_tth_real.py -q
"""
import os
import shutil
import subprocess

import pytest

from terai_router.tth import TTH, WayuEngine, duration

pytestmark = pytest.mark.skipif(os.environ.get('TERAI_TTH_REAL') != '1', reason='set TERAI_TTH_REAL=1 to run')

TEXT = 'สวัสดีครับ/ค่ะ นี่คือ TTH ของ TER-AI ทดสอบ 12 × 7 = 84'


@pytest.mark.skipif(not WayuEngine.available(), reason='wayu_tts not installed')
def test_real_wayu(tmp_path):
    out = str(tmp_path / 'wayu.wav')
    r = TTH(engine='wayu', fallback=False).synthesize(TEXT, out)
    assert r['engine'] == 'wayu' and r['chunks'] == 1
    assert 2.0 < r['seconds'] < 20.0
    if shutil.which('ffprobe'):
        probe = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'stream=sample_rate,channels', '-of',
                                'csv=p=0', out], capture_output=True, text=True).stdout.strip()
        assert probe == '24000,1'
        assert abs(duration(out) - r['seconds']) < 0.05
