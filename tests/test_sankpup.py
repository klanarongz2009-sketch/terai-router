"""SANKPUP: offline engine, SVG sanitizer, PNG/JPG rendering, Gemma fallback and the CLI."""
import io
import json

import pytest

from terai_router import cli as terai_cli
from terai_router.sankpup import Artwork, SvgError, generate, gemma, offline, save
from terai_router.sankpup.render import available_renderers, render
from terai_router.sankpup.sanitize import clean_model_output, extract_svg, sanitize_svg

needs_renderer = pytest.mark.skipif(not available_renderers(), reason='no SVG renderer installed')

PROMPTS = ['แมวสีส้มนั่งบนดวงจันทร์', 'บ้านหลังเล็กกับต้นไม้สองต้น ตอนกลางคืน', 'เรือใบสีแดงกลางทะเล',
           'an orange cat sitting on the moon', 'a robot holding a flower', 'mountains at sunset', 'xyzzy']


# ---- offline engine -------------------------------------------------------

@pytest.mark.parametrize('prompt', PROMPTS)
def test_offline_is_valid_and_survives_sanitizer(prompt):
    svg = offline.generate_svg(prompt, seed=0)
    assert svg.startswith('<svg') and svg.endswith('</svg>')
    clean, report = sanitize_svg(svg)
    assert report['removed_elements'] == 0 and report['removed_attributes'] == 0
    assert report['drawn'] > 0


def test_offline_is_deterministic_and_seeded():
    a = offline.generate_svg('แมวสีส้มนั่งบนดวงจันทร์', seed=3)
    assert a == offline.generate_svg('แมวสีส้มนั่งบนดวงจันทร์', seed=3)
    assert a != offline.generate_svg('แมวสีส้มนั่งบนดวงจันทร์', seed=4)


def test_offline_understands_thai_and_english():
    th = offline.compose('แมวสีส้มนั่งบนดวงจันทร์')
    en = offline.compose('an orange cat sitting on the moon')
    assert 'cat' in th['subjects'] and 'cat' in en['subjects']
    night = offline.compose('บ้านหลังเล็กกับต้นไม้สองต้น ตอนกลางคืน')
    assert 'house' in night['subjects'] and 'tree' in night['subjects'] and 'night' in night['scenes']


def test_generate_offline_and_empty_prompt():
    art = generate('จรวดบินไปดาวอังคาร', engine='offline')
    assert art.engine == 'offline' and art.model is None and art.svg.startswith('<svg')
    with pytest.raises(ValueError):
        generate('   ', engine='offline')
    with pytest.raises(ValueError):
        generate('cat', engine='dalle')


# ---- sanitizer ------------------------------------------------------------

def test_sanitizer_strips_active_content():
    dirty = ('<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
             'width="100" height="100" onload="alert(1)">'
             '<script>alert(1)</script><foreignObject><div>x</div></foreignObject>'
             '<image xlink:href="http://evil.example/x.png"/><use xlink:href="#a"/>'
             '<rect width="10" height="10" fill="url(http://evil.example/p)" onclick="x()"/>'
             '<circle cx="5" cy="5" r="4" style="fill:red;background:url(javascript:x)"/>'
             '<a href="javascript:alert(1)"><rect width="1" height="1"/></a></svg>')
    clean, report = sanitize_svg(dirty)
    low = clean.lower()
    for bad in ('script', 'onload', 'onclick', 'foreignobject', '<image', '<use', 'javascript', 'evil.example', '<a '):
        assert bad not in low, bad
    assert '<circle' in clean and 'fill:red' in clean
    assert report['removed_elements'] >= 5 and report['removed_attributes'] >= 2


@pytest.mark.parametrize('bad', [
    '',
    '<svg xmlns="http://www.w3.org/2000/svg"></svg>',
    '<html><rect width="1" height="1"/></html>',
    '<!DOCTYPE svg [<!ENTITY x "y">]><svg xmlns="http://www.w3.org/2000/svg"><rect width="1" height="1"/></svg>',
    '<svg><rect',
])
def test_sanitizer_rejects_unusable(bad):
    with pytest.raises(SvgError):
        sanitize_svg(bad)


def test_unclosed_paint_url():
    # Real Gemma 4 E2B output (bench prompt 5): fill="url(#sunsetGradient" rendered the whole image black.
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512"><radialGradient id="g">'
           '<stop offset="0" stop-color="#f40"/></radialGradient>'
           '<rect width="512" height="512" fill="url(#g"/><circle r="5" style="fill:url(#g"/>'
           '<rect width="5" height="5" fill="url(http://evil.example/x"/></svg>')
    clean, report = sanitize_svg(svg)
    assert 'fill="url(#g)"' in clean and 'fill:url(#g)' in clean
    assert 'evil' not in clean and report['removed_attributes'] == 1


def test_extract_and_repair_model_output():
    text = 'Here you go:\n```svg\n<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><circle cx="32" cy="32" r="20" fill="orange"/></svg>\n```\nEnjoy'
    assert extract_svg(text).startswith('<svg')
    svg, report = clean_model_output(text)
    assert report['repaired'] is False and 'circle' in svg
    truncated = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><g><rect width="10" height="10" fill="blue"/>'
    svg, report = clean_model_output(truncated)
    assert report['repaired'] is True and svg.endswith('</svg>')


# ---- rendering ------------------------------------------------------------

@needs_renderer
def test_render_png_and_jpg_are_real_non_blank_images():
    from PIL import Image
    svg = offline.generate_svg('แมวสีส้มนั่งบนดวงจันทร์')
    png = render(svg, 'png', 128)
    jpg = render(svg, 'jpg', 128)
    assert png[:8] == b'\x89PNG\r\n\x1a\n' and jpg[:3] == b'\xff\xd8\xff'
    for data, fmt in ((png, 'PNG'), (jpg, 'JPEG')):
        img = Image.open(io.BytesIO(data))
        assert img.format == fmt and img.size == (128, 128)
        lo, hi = img.convert('L').getextrema()
        assert hi - lo > 20  # not a single flat colour


def test_render_rejects_bad_format_and_size():
    svg = offline.generate_svg('cat')
    assert render(svg, 'svg') == svg.encode('utf-8')
    with pytest.raises(ValueError):
        render(svg, 'gif')
    with pytest.raises(ValueError):
        render(svg, 'png', 8)


@needs_renderer
def test_save_png_jpg_and_code(tmp_path):
    art = generate('ภูเขากับพระอาทิตย์ตก', engine='offline')
    files = save(art, tmp_path / 'm.png', size=64, save_code=True)
    assert [f.name for f in files] == ['m.png', 'm.svg']
    assert (tmp_path / 'm.svg').read_text(encoding='utf-8') == art.svg
    (jpg,) = save(art, tmp_path / 'm.jpeg', size=64)
    assert jpg.read_bytes()[:3] == b'\xff\xd8\xff'


# ---- Gemma backend (faked: no weights needed) ------------------------------

class FakeBackend:
    label = 'gemma-4-fake'

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def complete(self, messages, max_tokens=1500, temperature=0.4, seed=None, timeout=None):
        self.calls.append(messages)
        return self.replies.pop(0), {'completion_tokens': 10, 'seconds': 0.01, 'timed_out': False}


GOOD = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512"><rect width="512" height="512" fill="#123"/><circle cx="256" cy="256" r="90" fill="orange"/></svg>'


def test_gemma_retries_with_error_then_succeeds():
    fb = FakeBackend(['I cannot draw', GOOD])
    svg, info = gemma.draw_svg(fb, 'แมว', attempts=2, timeout=30)
    assert 'circle' in svg and len(info['attempts']) == 2 and 'error' in info['attempts'][0]
    assert 'SVG' in fb.calls[1][-1]['content'] or 'svg' in fb.calls[1][-1]['content']
    art = generate('แมว', engine='gemma', backend=FakeBackend([GOOD]))
    assert art.engine == 'gemma' and art.model == 'gemma-4-fake'


def test_gemma_failure_falls_back_to_offline_unless_disabled():
    art = generate('แมว', engine='gemma', backend=FakeBackend(['no', 'still no']))
    assert art.engine == 'offline' and 'usable SVG' in art.fallback_reason
    with pytest.raises(SvgError):
        generate('แมว', engine='gemma', backend=FakeBackend(['no', 'still no']), fallback=False)


def test_auto_uses_offline_without_weights(monkeypatch, tmp_path):
    monkeypatch.setenv('TERAI_MODELS_DIR', str(tmp_path))
    assert gemma.is_downloaded('e2b') is False
    assert generate('cat', engine='auto').engine == 'offline'


def test_models_are_official_gemma_4_ggufs():
    assert gemma.DEFAULT_MODEL == 'e2b'
    for key, spec in gemma.MODELS.items():
        assert spec.repo.startswith('google/gemma-4-') and spec.filename.endswith('.gguf') and len(spec.sha256) == 64


# ---- CLI ------------------------------------------------------------------

@needs_renderer
@pytest.mark.parametrize('ext', ['png', 'jpg', 'svg'])
def test_cli_writes_file(tmp_path, capsys, ext):
    out = tmp_path / f'cat.{ext}'
    rc = terai_cli.main(['sankpup', 'แมวสีส้มนั่งบนดวงจันทร์', '--engine', 'offline', '--size', '64', '-o', str(out), '--json'])
    assert rc == 0 and out.exists() and out.stat().st_size > 100
    report = json.loads(capsys.readouterr().out)
    assert report['engine'] == 'offline' and report['files'] == [str(out)]


def test_cli_errors(capsys, tmp_path):
    assert terai_cli.main(['sankpup']) == 2
    assert terai_cli.main(['sankpup', 'cat', '--size', '5', '-o', str(tmp_path / 'x.png')]) == 2
    assert terai_cli.main(['sankpup', '--list-models']) == 0
    out = capsys.readouterr().out
    assert 'e2b' in out and 'Apache License 2.0' in out
