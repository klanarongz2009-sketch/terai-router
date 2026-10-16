"""Web search tests. The network is never used: every fetch is a fake."""
import socket

import pytest

from terai_router.chat import Chat
from terai_router.websearch import CONT, WebSearch, cover, extract, passages, query_text

NOW = '2026-10-16T16:00:00'


def wiki(*pages):
    return {'query': {'pages': [dict(p, index=i + 1) for i, p in enumerate(pages)]}}


PM = {'title': 'นายกรัฐมนตรีญี่ปุ่น', 'fullurl': 'https://th.wikipedia.org/wiki/นายกรัฐมนตรีญี่ปุ่น',
      'extract': 'นายกรัฐมนตรีญี่ปุ่น เป็นหัวหน้ารัฐบาลของประเทศญี่ปุ่น ได้รับแต่งตั้งโดยจักรพรรดิ '
                 'หลังจากได้รับการเสนอชื่อจากสภาไดเอ็ต นายกรัฐมนตรีคนปัจจุบันคือ ทดสอบ ชื่อสมมุติ ดำรงตำแหน่งตั้งแต่ปี 2026'}
NOISE = {'title': 'ซาบะ', 'fullurl': 'https://th.wikipedia.org/wiki/ซาบะ',
         'extract': 'ซาบะ เป็นปลาทะเลชนิดหนึ่ง นิยมนำมาย่างกับเกลือ พบมากในประเทศญี่ปุ่นและเกาหลี'}


class Fake:
    def __init__(self, by_host=None, error=None):
        self.by_host, self.error, self.urls = by_host or {}, error, []

    def __call__(self, url):
        self.urls.append(url)
        if self.error:
            raise self.error
        for host, data in self.by_host.items():
            if host in url:
                return data
        return {'query': {}}


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def boom(*a, **k):
        raise AssertionError('real network used in a test')
    monkeypatch.setattr(socket, 'create_connection', boom)
    monkeypatch.setattr('urllib.request.urlopen', boom)


def ws(fake, **kw):
    return WebSearch(enabled=True, cache_dir=None, fetch=fake, **kw)


def test_disabled_makes_no_request():
    fake = Fake({'th.wikipedia': wiki(PM)})
    w = WebSearch(enabled=False, cache_dir=None, fetch=fake)
    assert w.search('นายกรัฐมนตรีญี่ปุ่นคือใคร') is None
    assert fake.urls == [] and w.calls == 0


def test_chat_default_is_offline():
    c = Chat(now=NOW, seed=1)
    assert c.web is None
    out = c.reply('ซาบาริโนวาลิกซ์คืออะไร')
    assert out.startswith('ผมไม่รู้') and 'ค้น' not in out


def test_query_text_strips_question_words():
    assert query_text('ใครคือนายกรัฐมนตรีคนปัจจุบันของญี่ปุ่นครับ') == 'นายกรัฐมนตรีคนปัจจุบันของญี่ปุ่น'


def test_wiki_request_has_api_params():
    fake = Fake({'th.wikipedia': wiki(PM)})
    ws(fake).search('ใครคือนายกรัฐมนตรีคนปัจจุบันของญี่ปุ่น')
    u = fake.urls[0]
    assert u.startswith('https://th.wikipedia.org/w/api.php?')
    for p in ('generator=search', 'prop=extracts', 'exintro=1', 'explaintext=1', 'inprop=url'):
        assert p in u.replace('%7C', '|')


def test_rank_and_cite_current_answer():
    fake = Fake({'th.wikipedia': wiki(NOISE, PM)})
    hit = ws(fake).search('ใครคือนายกรัฐมนตรีคนปัจจุบันของญี่ปุ่น')
    assert hit['title'] == 'นายกรัฐมนตรีญี่ปุ่น'  # our ranking, not the engine's order
    assert 'คนปัจจุบันคือ ทดสอบ' in hit['answer']
    cite = WebSearch.cite(hit)
    assert 'Wikipedia ภาษาไทย' in cite and hit['url'] in cite and 'CC BY-SA 4.0' in cite


def test_made_up_word_is_not_answered():
    fake = Fake({'th.wikipedia': wiki(NOISE), 'en.wikipedia': wiki(NOISE)})
    assert cover('ซาบาริโนวาลิกซ์คืออะไร', NOISE['title'] + NOISE['extract']) < 0.6
    assert ws(fake).search('ซาบาริโนวาลิกซ์คืออะไร') is None
    assert len(fake.urls) == 2  # th then en


def test_english_fallback():
    en = {'title': 'Prime Minister of Japan', 'fullurl': 'https://en.wikipedia.org/wiki/Prime_Minister_of_Japan',
          'extract': 'The prime minister of Japan is the head of government of Japan. The current prime minister is Test Person.'}
    fake = Fake({'th.wikipedia': {'query': {}}, 'en.wikipedia': wiki(en)})
    hit = ws(fake).search('who is the current prime minister of japan')
    assert hit['source'] == 'Wikipedia ภาษาอังกฤษ' and 'Test Person' in hit['answer']


def test_searx_used_last():
    sx = {'results': [{'title': 'นายกรัฐมนตรีญี่ปุ่น', 'url': 'https://example.org/pm',
                       'content': 'นายกรัฐมนตรีญี่ปุ่นคนปัจจุบันคือ ทดสอบ ชื่อสมมุติ'}]}
    fake = Fake({'searx.local': sx})
    hit = ws(fake, searx='http://searx.local/').search('ใครคือนายกรัฐมนตรีคนปัจจุบันของญี่ปุ่น')
    assert fake.urls[-1].startswith('http://searx.local/search?') and 'format=json' in fake.urls[-1]
    assert hit['source'] == 'SearXNG (example.org)'


def test_offline_error_falls_back():
    fake = Fake(error=OSError('Network is unreachable'))
    c = Chat(now=NOW, seed=1, websearch=ws(fake))
    out = c.reply('ซาบาริโนวาลิกซ์คืออะไร')
    assert out.startswith('ผมไม่รู้') and 'ค้นเว็บไม่สำเร็จ (OSError)' in out
    # the knowledge pack still answers while offline
    assert 'ดาวเคราะห์' in c.reply('ดาวอังคารคืออะไร')


def test_pack_first_when_confident():
    fake = Fake({'th.wikipedia': wiki(PM)})
    c = Chat(now=NOW, seed=1, websearch=ws(fake))
    out = c.reply('ดาวอังคารคืออะไร')
    assert 'ดาวเคราะห์' in out and '[ค้นเว็บ]' not in out
    assert fake.urls == []


def test_chat_web_answer_for_current_question():
    fake = Fake({'th.wikipedia': wiki(NOISE, PM)})
    c = Chat(now=NOW, seed=1, websearch=ws(fake))
    out = c.reply('ใครคือนายกรัฐมนตรีคนปัจจุบันของญี่ปุ่น')
    assert out.startswith('[ค้นเว็บ]') and 'ทดสอบ' in out and 'https://th.wikipedia.org/wiki/' in out


def test_no_match_message():
    fake = Fake({'th.wikipedia': wiki(NOISE), 'en.wikipedia': {'query': {}}})
    out = Chat(now=NOW, seed=1, websearch=ws(fake)).reply('ซาบาริโนวาลิกซ์คืออะไร')
    assert 'ค้น Wikipedia ไทยและอังกฤษแล้วก็ไม่พบ' in out


def test_disk_cache(tmp_path):
    fake = Fake({'th.wikipedia': wiki(PM)})
    w = WebSearch(enabled=True, cache_dir=str(tmp_path), fetch=fake)
    q = 'ใครคือนายกรัฐมนตรีคนปัจจุบันของญี่ปุ่น'
    assert w.search(q) and w.search(q)
    assert w.calls == 1 and len(list(tmp_path.iterdir())) == 1


def test_cli_flags(monkeypatch, capsys, tmp_path):
    import io
    from terai_router import cli
    seen = {}

    class Spy(Chat):
        def __init__(self, **kw):
            seen.update(kw)
            kw['websearch'] = ws(Fake({'th.wikipedia': wiki(PM)}))
            kw.pop('web'), kw.pop('searx')
            super().__init__(**kw)
    monkeypatch.setattr('terai_router.chat.Chat', Spy)
    monkeypatch.setattr('sys.stdin', io.StringIO('ใครคือนายกรัฐมนตรีคนปัจจุบันของญี่ปุ่น\n'))
    cli.main(['chat', '--searx', 'http://s.local', '--session', str(tmp_path / 's.json')])
    assert seen['searx'] == 'http://s.local'
    assert '[ค้นเว็บ]' in capsys.readouterr().out


JP_LEAD = ('นายกรัฐมนตรีญี่ปุ่น (อังกฤษ: Prime Minister of Japan) ภาษาญี่ปุ่นเรียก ไนกากุโซริไดจิง '
           '(ญี่ปุ่น: 内閣総理大臣 Naikaku-sōri-daijin) หรือ ชูโช (ญี่ปุ่น: 首相 Shushō) '
           'เป็นหัวหน้ารัฐบาลญี่ปุ่นและผู้บัญชาการสูงสุดของกองกำลังป้องกันตนเองญี่ปุ่น '
           'จักรพรรดิทรงแต่งตั้งนายกรัฐมนตรีตามที่สภานิติบัญญัติแห่งชาติถวายชื่อ '
           'นายกรัฐมนตรีต้องได้รับความไว้วางใจจากสภาผู้แทนราษฎรให้ดำรงตำแหน่ง '
           'นายกรัฐมนตรีเป็นหัวหน้าคณะรัฐมนตรี และรัฐมนตรีคนอื่น ๆ จะดำรงตำแหน่งตามอัธยาศัยของนายกรัฐมนตรี '
           'นายกรัฐมนตรีคนปัจจุบัน คือ ซานาเอะ ทากาอิจิ ดำรงตำแหน่งตั้งแต่ 21 ตุลาคม พ.ศ. 2568')


def test_passages_start_at_clause_start():
    ps = passages(JP_LEAD)
    assert ' '.join(ps) == JP_LEAD
    for p in ps:
        assert not p.startswith(CONT), p
        assert p.count('(') == p.count(')'), p
    ans = extract('ใครคือนายกรัฐมนตรีคนปัจจุบันของญี่ปุ่น', JP_LEAD)
    assert not ans.startswith(CONT) and ' ๆ จะดำรง' not in ans.split(')')[-1][:12]
    assert 'นายกรัฐมนตรีคนปัจจุบัน คือ ซานาเอะ ทากาอิจิ' in ans


def test_passages_keep_english_sentences_whole():
    t = 'Mars is the fourth planet from the Sun and the second smallest. It has a thin atmosphere, mostly carbon dioxide.'
    for p in passages(t):
        assert p[0].isupper() and p.endswith('.')
