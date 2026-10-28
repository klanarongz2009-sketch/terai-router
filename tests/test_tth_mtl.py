"""TTH-MTL (engine 'mtl', OmniVoice by k2-fsa), with a fake `omnivoice` module: no weights, no torch needed."""
import sys
import types

import pytest

from terai_router import cli
from terai_router import tth as T
from terai_router.tth import TTH


class FakeOmni:
    """Stands in for omnivoice.OmniVoice and records what TTH asks of it."""
    loads = []
    sampling_rate = 24000

    def __init__(self):
        self.prompts, self.calls = [], []

    @classmethod
    def from_pretrained(cls, name, **kw):
        cls.loads.append((name, kw))
        return cls()

    def create_voice_clone_prompt(self, ref_audio, ref_text=None):
        self.prompts.append((ref_audio, ref_text))
        return ('prompt', ref_audio)

    def generate(self, text, language=None, generation_config=None, **kw):
        self.calls.append({'text': text, 'language': language, 'num_step': generation_config.num_step, **kw})
        return [[0.1] * 2400]                                   # 0.1 s at 24 kHz


class FakeConfig:
    def __init__(self, num_step=32):
        self.num_step = num_step


@pytest.fixture
def fake_omnivoice(monkeypatch):
    FakeOmni.loads = []
    pkg = types.ModuleType('omnivoice')
    pkg.OmniVoice = FakeOmni
    models = types.ModuleType('omnivoice.models')
    mod = types.ModuleType('omnivoice.models.omnivoice')
    mod.OmniVoiceGenerationConfig = FakeConfig
    monkeypatch.setitem(sys.modules, 'omnivoice', pkg)
    monkeypatch.setitem(sys.modules, 'omnivoice.models', models)
    monkeypatch.setitem(sys.modules, 'omnivoice.models.omnivoice', mod)
    monkeypatch.setattr(T.MtlEngine, 'available', staticmethod(lambda: True))
    return FakeOmni


class FakeWayu:
    """Renders the Thai reference clip that TTH-MTL clones."""

    def __init__(self, installed=True):
        self.installed, self.calls = installed, []

    def available(self):
        return self.installed

    def synthesize(self, chunks, voice, speed, seed, out):
        self.calls.append((list(chunks), voice, speed, seed))
        T.write_wav(out, [0.0] * 4800, 24000)


def mtl_tth(tmp_path, wayu=None, **kw):
    lang = kw.pop('lang', 'th')
    eng = T.MtlEngine(lang=lang, ref_audio=kw.pop('ref_audio', None),
                      ref_text=kw.pop('ref_text', None), cache_dir=str(tmp_path / 'cache'),
                      wayu=wayu if wayu is not None else FakeWayu())
    return TTH(engine='mtl', lang=lang, engines={'mtl': eng, 'wayu': FakeWayu(False), 'edge': FakeWayu(False)},
               **kw), eng


def test_mtl_is_opt_in_and_falls_back_to_thai_engines():
    assert 'mtl' in T.ENGINES and T.FALLBACK_ENGINES == ('wayu', 'edge')
    assert TTH().order() == ['wayu', 'edge']                    # auto never picks the 3.3 GB engine
    assert TTH(engine='mtl').order() == ['mtl', 'wayu', 'edge']
    assert TTH(engine='mtl', fallback=False).order() == ['mtl']
    assert TTH(engine='mtl', lang='en').order() == ['mtl']      # Wayu/edge cannot read English text
    assert set(T.installed_engines()) == {'wayu', 'edge', 'mtl'}


def test_other_languages_need_mtl_and_skip_the_thai_frontend():
    with pytest.raises(ValueError):
        TTH(lang='en')
    t = TTH(engine='mtl', lang='en')
    spoken, pieces = t.plan('TER-AI   version 0.12 costs 1,250 baht.')
    assert spoken == 'TER-AI version 0.12 costs 1,250 baht.' and pieces == [spoken]
    spoken_th, _ = TTH(engine='mtl').plan('TER-AI ราคา 1,250 บาท')
    assert spoken_th == T.prepare('TER-AI ราคา 1,250 บาท', 'ค่ะ')


def test_bad_mtl_arguments(tmp_path):
    with pytest.raises(ValueError):
        TTH(engine='mtl', ref_audio=str(tmp_path / 'missing.wav'))
    with pytest.raises(ValueError):
        TTH(engine='mtl', mtl_steps=0)


def test_thai_clones_a_cached_wayu_reference(tmp_path, fake_omnivoice):
    wayu = FakeWayu()
    t, eng = mtl_tth(tmp_path, wayu=wayu, voice='m_young_clear')
    r = t.synthesize('สวัสดีครับ/ค่ะ ราคา 1,250 บาท', str(tmp_path / 'a.wav'))
    assert r['engine'] == 'mtl' and r['voice'] == 'm_young_clear' and r['online'] is False
    assert abs(r['seconds'] - 0.1) < 1e-6
    assert fake_omnivoice.loads[0][0] == 'k2-fsa/OmniVoice' and fake_omnivoice.loads[0][1]['device_map'] == 'cpu'
    assert wayu.calls == [([T.MTL_REF_TEXT['m']], 'm_young_clear', 1.0, 0)]
    ov = eng._ov
    assert ov.prompts[0][1] == T.MTL_REF_TEXT['m'] and ov.prompts[0][0].endswith('ref-m_young_clear.wav')
    call = ov.calls[0]
    assert call['language'] == 'th' and call['num_step'] == T.MTL_STEPS == 16
    assert call['text'] == 'สวัสดีครับ ราคา หนึ่งพันสองร้อยห้าสิบ บาท'
    assert call['voice_clone_prompt'][0] == 'prompt' and 'instruct' not in call and 'speed' not in call
    t.synthesize('อีกครั้ง', str(tmp_path / 'b.wav'))             # reference clip and prompt are cached
    assert len(wayu.calls) == 1 and len(ov.prompts) == 1


def test_english_designs_a_voice_and_keeps_text(tmp_path, fake_omnivoice):
    wayu = FakeWayu()
    t, eng = mtl_tth(tmp_path, wayu=wayu, lang='en', speed=1.2)
    r = t.synthesize('Hello from TER-AI 0.12.', str(tmp_path / 'en.wav'))
    call = eng._ov.calls[0]
    assert r['engine'] == 'mtl' and call['language'] == 'en' and call['text'] == 'Hello from TER-AI 0.12.'
    assert call['instruct'] == 'female, young adult' and call['speed'] == 1.2
    assert not wayu.calls                                        # no Thai reference for another language


def test_own_reference_clip_and_thai_without_wayu(tmp_path, fake_omnivoice):
    clip = tmp_path / 'me.wav'
    T.write_wav(str(clip), [0.0] * 2400, 24000)
    t, eng = mtl_tth(tmp_path, ref_audio=str(clip), ref_text='สวัสดี')
    t.synthesize('ทดสอบ', str(tmp_path / 'a.wav'))
    assert eng._ov.prompts == [(str(clip), 'สวัสดี')]
    t, eng = mtl_tth(tmp_path, wayu=FakeWayu(False), voice='m_mid_warm')
    t.synthesize('ทดสอบ', str(tmp_path / 'b.wav'))
    assert eng._ov.calls[0]['instruct'] == 'male, young adult' and not eng._ov.prompts


def test_mtl_failure_falls_back_to_wayu(tmp_path, fake_omnivoice, monkeypatch):
    class Boom(T.MtlEngine):
        def synthesize(self, *a):
            raise RuntimeError('out of memory')

    class OkWayu(FakeWayu):
        def voice_for(self, voice):
            return T.WayuEngine().voice_for(voice)

    t = TTH(engine='mtl', engines={'mtl': Boom(), 'wayu': OkWayu(), 'edge': FakeWayu(False)})
    r = t.synthesize('ทดสอบ', str(tmp_path / 'a.wav'))
    assert r['engine'] == 'wayu' and r['fallback_used'] and r['errors'][0].startswith('mtl: RuntimeError')


def test_cli_mtl_options(tmp_path, capsys, monkeypatch):
    seen = {}

    def fake(self, text, out):
        seen.update(engine=self.engine, lang=self.lang, order=self.order(), mtl=self.engines['mtl'])
        T.write_wav(out, [0.0] * 2400, 24000)
        return {'out': out, 'engine': 'mtl', 'voice': 'f_young_clear', 'online': False, 'fallback_used': False,
                'chunks': 1, 'text': text, 'seconds': 0.1, 'errors': []}

    monkeypatch.setattr(T.TTH, 'synthesize', fake)
    out = str(tmp_path / 'x.wav')
    assert cli.main(['tth', '--engine', 'mtl', '--lang', 'en', '--mtl-steps', '8', '-o', out, 'Hello']) == 0
    assert seen['engine'] == 'mtl' and seen['lang'] == 'en' and seen['order'] == ['mtl']
    assert seen['mtl'].num_step == 8 and seen['mtl'].lang == 'en'
    assert 'engine=mtl' in capsys.readouterr().out
    with pytest.raises(SystemExit):
        cli.main(['tth', '--lang', 'en', 'Hello'])              # English without --engine mtl
    assert cli.main(['tth', '--list-voices']) == 0
    assert 'TTH-MTL' in capsys.readouterr().out
    assert cli.main(['tth', '--engines']) == 0
    assert '\nmtl\t' in capsys.readouterr().out
