"""TTH tests that need no speech model and no network: text frontend, chunking, engine choice, CLI."""
import json
import os
import wave

import pytest

from terai_router import cli
from terai_router import tth as T
from terai_router.tth import TTH, chunk, prepare, read_int, read_number


# ------------------------------------------------------------------ numbers

@pytest.mark.parametrize('n,words', [
    ('0', 'ศูนย์'), ('1', 'หนึ่ง'), ('10', 'สิบ'), ('11', 'สิบเอ็ด'), ('20', 'ยี่สิบ'), ('21', 'ยี่สิบเอ็ด'),
    ('101', 'หนึ่งร้อยเอ็ด'), ('211', 'สองร้อยสิบเอ็ด'), ('2569', 'สองพันห้าร้อยหกสิบเก้า'),
    ('8,192', 'แปดพันหนึ่งร้อยเก้าสิบสอง'), ('1000000', 'หนึ่งล้าน'), ('1000001', 'หนึ่งล้านหนึ่ง'),
    ('11000000', 'สิบเอ็ดล้าน'), ('21500000', 'ยี่สิบเอ็ดล้านห้าแสน'),
    ('1000000000000', 'หนึ่งล้านล้าน'), ('095', 'ศูนย์เก้าห้า'),
])
def test_read_int(n, words):
    assert read_int(n) == words


def test_read_number_decimal_and_long():
    assert read_number('97.6') == 'เก้าสิบเจ็ดจุดหก'
    assert read_number('3.14') == 'สามจุดหนึ่งสี่'
    assert read_number('1234567890123456') == T.read_digits('1234567890123456')  # over 15 digits


# ------------------------------------------------------------------ prepare

def test_prepare_politeness_follows_choice():
    assert prepare('สวัสดีครับ/ค่ะ', 'ครับ') == 'สวัสดีครับ'
    assert prepare('สวัสดีครับ/ค่ะ', 'ค่ะ') == 'สวัสดีค่ะ'
    assert prepare('ได้ไหมครับ/คะ', 'ค่ะ') == 'ได้ไหมคะ'
    with pytest.raises(ValueError):
        prepare('x', 'จ้ะ')


def test_prepare_math_percent_and_router_style_numbers():
    assert prepare('12 × 7 = 84 ครับ/ค่ะ', 'ค่ะ') == 'สิบสอง คูณ เจ็ด เท่ากับ แปดสิบสี่ ค่ะ'
    assert prepare('15% ของ 200') == 'สิบห้าเปอร์เซ็นต์ ของ สองร้อย'
    assert prepare('-3 + 4') == 'ลบสาม บวก สี่'
    assert prepare('เลข ๑๒๓') == 'เลข หนึ่งร้อยยี่สิบสาม'  # Thai digits, as the router normalizer folds them


def test_prepare_time_version_abbreviation():
    assert prepare('ตอนนี้เวลา 14:05 น. ครับ') == 'ตอนนี้เวลา สิบสี่ นาฬิกา ห้า นาที ครับ'
    assert prepare('09:00 น.') == 'เก้า นาฬิกา'
    assert prepare('v0.10.0') == 'เวอร์ชัน ศูนย์จุดสิบจุดศูนย์'
    assert prepare('ม.4 พ.ศ. 2569') == 'มอสี่ พุทธศักราช สองพันห้าร้อยหกสิบเก้า'
    assert prepare('12.5 กม.') == 'สิบสองจุดห้า กิโลเมตร'


def test_prepare_english_terms():
    assert prepare('TER-AI ใช้ TTH') == 'เธอเอไอ ใช้ ทีทีเอช'
    assert prepare('ใช้ GPU กับ API') == 'ใช้ จีพียู กับ เอพีไอ'      # acronyms spelled with Thai letter names
    assert prepare('OpenAI และ pytest') == 'OpenAI และ pytest'          # other English words stay for the engine


def test_prepare_drops_links_emoji_and_keeps_citation_source():
    s = prepare('[ค้นเว็บ] ดาวอังคาร (ที่มา: Wikipedia ภาษาไทย "ดาวอังคาร", https://th.wikipedia.org/wiki/x, CC BY-SA 4.0) 😀')
    assert s == 'จากการค้นเว็บ ดาวอังคาร ที่มา วิกิพีเดีย ภาษาไทย ดาวอังคาร'
    assert 'http' not in prepare('ดู https://example.com/a?b=1 หรือ www.example.org')
    assert prepare('บรรทัดแรก\n\n  \nบรรทัดสอง') == 'บรรทัดแรก\nบรรทัดสอง'
    assert prepare('   ') == ''


# ------------------------------------------------------------------ chunk

def test_chunk_packs_at_spaces_and_lines():
    text = prepare('ไม่มีตัวเลข ไม่มีสัญลักษณ์ ข้อความไทยล้วน ยาวพอที่จะต้องตัดเป็นหลายท่อน เพื่อทดสอบ\nบรรทัดใหม่')
    parts = chunk(text, 40)
    assert all(len(p) <= 40 for p in parts)
    assert parts[-1] == 'บรรทัดใหม่'                     # a line break always ends a chunk
    assert ' '.join(parts).replace(' ', '') == text.replace('\n', '').replace(' ', '')


def test_chunk_hard_split_respects_thai_marks():
    s = 'เ' * 5 + 'กิ' * 100
    parts = chunk(s, 20)
    assert ''.join(parts) == s
    assert all(len(p) <= 20 for p in parts)
    for p in parts[1:]:
        assert p[0] not in T._COMBINING                   # never starts with a vowel/tone mark
    for p in parts[:-1]:
        assert p[-1] not in T._LEADING                    # never ends with a leading vowel
    with pytest.raises(ValueError):
        chunk('abc', 4)


def test_default_chunk_size_is_90():
    assert T.MAX_CHARS == 90
    assert all(len(p) <= 90 for p in chunk(prepare('ก' * 300)))


# ------------------------------------------------------------------ engines (mocked)

class FakeEngine:
    def __init__(self, name, ok=True, installed=True, online=False):
        self.name, self.ok, self.installed, self.online = name, ok, installed, online
        self.calls = []

    def available(self):
        return self.installed

    def voice_for(self, voice):
        return (T.EdgeEngine if self.name == 'edge' else T.WayuEngine)().voice_for(voice)

    def synthesize(self, chunks, voice, speed, seed, out):
        self.calls.append((list(chunks), voice, speed, seed, out))
        if not self.ok:
            raise OSError('offline')
        T.write_wav(out, [0.0] * 2400, 24000)          # 0.1 s of silence


def make(wayu=True, edge=True, wayu_ok=True, edge_ok=True, **kw):
    engines = {'wayu': FakeEngine('wayu', wayu_ok, wayu), 'edge': FakeEngine('edge', edge_ok, edge, online=True)}
    return TTH(engines=engines, **kw), engines


def test_auto_prefers_local_wayu(tmp_path):
    t, e = make()
    r = t.synthesize('สวัสดีครับ/ค่ะ', str(tmp_path / 'a.wav'))
    assert r['engine'] == 'wayu' and r['voice'] == 'f_young_clear' and not r['fallback_used']
    assert e['wayu'].calls[0][0] == ['สวัสดีค่ะ']             # female default voice says ค่ะ
    assert abs(r['seconds'] - 0.1) < 1e-6 and r['online'] is False
    assert not e['edge'].calls


def test_falls_back_to_edge_when_wayu_fails(tmp_path):
    t, e = make(wayu_ok=False, voice='m_young_clear')
    r = t.synthesize('สวัสดีครับ/ค่ะ', str(tmp_path / 'a.wav'))
    assert r['engine'] == 'edge' and r['fallback_used'] and r['online'] is True
    assert r['voice'] == 'th-TH-NiwatNeural'                # same gender as the Wayu voice
    assert e['edge'].calls[0][0] == ['สวัสดีครับ']
    assert r['errors'] and r['errors'][0].startswith('wayu: OSError')


def test_falls_back_when_wayu_not_installed(tmp_path):
    t, e = make(wayu=False)
    r = t.synthesize('ทดสอบ', str(tmp_path / 'a.wav'))
    assert r['engine'] == 'edge' and r['voice'] == 'th-TH-PremwadeeNeural'
    assert r['errors'] == ['wayu: not installed']


def test_no_fallback_and_no_engine(tmp_path):
    t, _ = make(wayu_ok=False, fallback=False)
    with pytest.raises(T.TTHError):
        t.synthesize('ทดสอบ', str(tmp_path / 'a.wav'))
    t, _ = make(wayu=False, edge=False)
    with pytest.raises(T.TTHUnavailable):
        t.synthesize('ทดสอบ', str(tmp_path / 'a.wav'))


def test_edge_voice_and_explicit_engine_order():
    assert make(voice='th-TH-NiwatNeural')[0].order() == ['edge', 'wayu']
    assert make(engine='edge')[0].order() == ['edge', 'wayu']
    assert make(engine='wayu', fallback=False)[0].order() == ['wayu']
    t, _ = make(voice='th-TH-NiwatNeural')
    assert t.polite == 'ครับ'
    assert T.WayuEngine().voice_for('th-TH-NiwatNeural') == 'm_young_clear'
    assert T.EdgeEngine().voice_for('f_mid_warm') == 'th-TH-PremwadeeNeural'


def test_bad_arguments(tmp_path):
    with pytest.raises(ValueError):
        TTH(speed=3)
    with pytest.raises(ValueError):
        TTH(voice='robot')
    with pytest.raises(ValueError):
        TTH(engine='paxa-cloud')
    t, _ = make()
    with pytest.raises(ValueError):
        t.synthesize('ทดสอบ', str(tmp_path / 'a.ogg'))
    with pytest.raises(ValueError):
        t.synthesize('  ', str(tmp_path / 'a.wav'))


def test_write_wav_format(tmp_path):
    p = str(tmp_path / 's.wav')
    T.write_wav(p, [0.5, -0.5, 2.0], 24000)
    with wave.open(p) as w:
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()) == (1, 2, 24000, 3)


# ------------------------------------------------------------------ CLI

def test_cli_dry_run(capsys):
    assert cli.main(['tth', '--dry-run', '--voice', 'm_young_clear', '12 × 7 = 84 ครับ/ค่ะ']) == 0
    assert capsys.readouterr().out == '1\tสิบสอง คูณ เจ็ด เท่ากับ แปดสิบสี่ ครับ\n'
    assert cli.main(['tth', '--dry-run', '--json', 'สวัสดีครับ/ค่ะ']) == 0
    d = json.loads(capsys.readouterr().out)
    assert d['chunks'] == ['สวัสดีค่ะ'] and d['engines'] == ['wayu', 'edge'] and d['polite'] == 'ค่ะ'


def test_cli_reads_file_and_stdin(tmp_path, capsys, monkeypatch):
    f = tmp_path / 'in.txt'
    f.write_text('ไฟล์ 2 บรรทัด', encoding='utf-8')
    assert cli.main(['tth', '--dry-run', '-f', str(f)]) == 0
    assert capsys.readouterr().out == '1\tไฟล์ สอง บรรทัด\n'
    import io
    monkeypatch.setattr('sys.stdin', io.StringIO('จาก stdin'))
    assert cli.main(['tth', '--dry-run', '-']) == 0
    assert capsys.readouterr().out == '1\tจาก stdin\n'


def test_cli_list_voices_and_engines(capsys):
    assert cli.main(['tth', '--list-voices']) == 0
    out = capsys.readouterr().out
    assert 'f_young_clear  (default)' in out and 'th-TH-PremwadeeNeural' in out and 'CC-BY-NC-4.0' in out
    assert cli.main(['tth', '--engines']) == 0
    out = capsys.readouterr().out
    assert out.startswith('wayu\t') and '\nedge\t' in out


@pytest.mark.parametrize('args', [['tth'], ['tth', '--speed', '5', 'x'], ['tth', '--voice', 'robot', 'x'],
                                  ['tth', '--engine', 'cloud', 'x'], ['tth', '-o', 'a.ogg', 'x']])
def test_cli_rejects_bad_args(args, monkeypatch):
    monkeypatch.setattr(T.TTH, 'synthesize', lambda self, text, out: (_ for _ in ()).throw(ValueError('bad out')))
    with pytest.raises(SystemExit) as e:
        cli.main(args)
    assert e.value.code == 2


def test_cli_synthesize_reports(tmp_path, capsys, monkeypatch):
    seen = {}

    def fake(self, text, out):
        seen.update(text=text, out=out, voice=self.voice, speed=self.speed, engine=self.engine, fb=self.fallback)
        return {'out': out, 'engine': 'edge', 'voice': 'th-TH-NiwatNeural', 'online': True, 'fallback_used': True,
                'chunks': 1, 'text': text, 'seconds': 1.5, 'errors': ['wayu: not installed']}
    monkeypatch.setattr(T.TTH, 'synthesize', fake)
    out = str(tmp_path / 'x.mp3')
    assert cli.main(['tth', '-o', out, '--voice', 'm_young_clear', '--speed', '1.2', '--no-fallback', 'สวัสดี']) == 0
    cap = capsys.readouterr()
    assert cap.out == out + '\t1.50 s\tengine=edge voice=th-TH-NiwatNeural chunks=1 (fallback)\n'
    assert 'skipped wayu: not installed' in cap.err
    assert seen == {'text': 'สวัสดี', 'out': out, 'voice': 'm_young_clear', 'speed': 1.2, 'engine': 'auto', 'fb': False}


def test_cli_engine_failure_exit_code(capsys, monkeypatch):
    monkeypatch.setattr(T.TTH, 'synthesize', lambda self, text, out: (_ for _ in ()).throw(T.TTHUnavailable('none')))
    assert cli.main(['tth', 'สวัสดี']) == 2
    assert 'terai tth: none' in capsys.readouterr().err


def test_chat_speak_hook(tmp_path, capsys, monkeypatch):
    spoken = []

    def fake(self, text, out):
        spoken.append((text, out))
        T.write_wav(out, [0.0] * 240, 24000)
        return {'out': out, 'engine': 'wayu', 'voice': self.voice, 'online': False, 'fallback_used': False,
                'chunks': 1, 'text': text, 'seconds': 0.01, 'errors': []}
    monkeypatch.setattr(T.TTH, 'synthesize', fake)
    import io
    monkeypatch.setattr('sys.stdin', io.StringIO('12 × 7\n'))
    folder = tmp_path / 'tth'
    rc = cli.main(['chat', '--session', str(tmp_path / 's.json'), '--speak', '--speak-dir', str(folder),
                   '--player', 'none'])
    assert rc == 0
    cap = capsys.readouterr()
    assert len(spoken) == 1 and '84' in spoken[0][0]
    assert spoken[0][1] == os.path.join(str(folder), 'reply-001.wav') and os.path.exists(spoken[0][1])
    assert '[tth] ' in cap.err and '[tth]' not in cap.out    # transcript on stdout stays clean
