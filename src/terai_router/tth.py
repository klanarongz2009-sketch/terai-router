"""TTH: Thai text-to-speech for TER-AI (the name comes from "TTS", with H for Thai).

TTH turns a Thai (or Thai-English) message into speech. It has two parts:

1. A text frontend written for TER-AI, pure Python with no dependencies: `prepare()` rewrites a message the
   way it should be spoken (numbers, times, versions, maths symbols, acronyms, the ครับ/ค่ะ slash, links and
   citations), and `chunk()` cuts it into short pieces. The same frontend is ported to `docs/tth.js` and
   checked for identical output by `eval/parity.py`.
2. Pluggable speech engines, both optional:
   - `wayu`: Wayu-Paxa-TTS-Edge, an 82M open-weight Thai model by Paxa Labs / Wayu Research (Kokoro-based),
     run locally on CPU. Install with the `tth` extra (Python 3.10+; see README). The weights
     are downloaded from Hugging Face (`wayu-ai/wayu-paxa-tts-edge`) on first use and are NOT part of this
     repository. Weights license: CC-BY-NC-4.0 (non-commercial, attribution to Paxa Labs / Wayu Research).
   - `edge`: edge-tts, an online Microsoft text-to-speech service (sends the text to Microsoft). Used as the
     fallback when Wayu is not installed or fails. Install with `pip install edge-tts`.
   - `mtl` (TTH-MTL, "TTH หลายภาษา", prototype, not released): OmniVoice by k2-fsa, an open-weight zero-shot TTS for 600+
     languages (Thai included), run locally on CPU. Opt in with `engine='mtl'` (it is never picked by `auto`:
     about 3.3 GB of weights and much slower than Wayu on CPU). Install with the `tth-mtl` extra (Python
     3.10+). The weights (`k2-fsa/OmniVoice`) are downloaded from Hugging Face on first use and are NOT part of
     this repository. Code Apache-2.0; weights CC-BY-NC (non-commercial, because of its training data such as
     Emilia). For Thai it clones a short Thai reference clip that Wayu reads (or your own `ref_audio`); other
     languages are spoken with `lang='en'`, `lang='ja'`, ... and skip the Thai text frontend.

    >>> from terai_router.tth import prepare, chunk
    >>> prepare('12 × 7 = 84 ครับ/ค่ะ', polite='ค่ะ')
    'สิบสอง คูณ เจ็ด เท่ากับ แปดสิบสี่ ค่ะ'

Use `TTH(...).synthesize(text, 'out.wav')` or the command line `terai tth "ข้อความ" -o out.wav`.
"""
import importlib.util
import os
import re
import shutil
import subprocess
import tempfile

# ---------------------------------------------------------------------------------------------------------
# Voices
# ---------------------------------------------------------------------------------------------------------

WAYU_MODEL = 'wayu-ai/wayu-paxa-tts-edge'
WAYU_VOICES = ['f_elderly_low', 'f_elderly_soft', 'f_mid_clear', 'f_mid_warm', 'f_teen_bright', 'f_young_bright',
               'f_young_clear', 'f_young_warm', 'm_elderly_deep', 'm_mid_warm', 'm_teen_bright', 'm_young_clear']
EDGE_VOICES = {'th-TH-PremwadeeNeural': 'f', 'th-TH-NiwatNeural': 'm', 'th-TH-AcharaNeural': 'f'}
DEFAULT_VOICE = 'f_young_clear'
DEFAULT_EDGE = {'f': 'th-TH-PremwadeeNeural', 'm': 'th-TH-NiwatNeural'}
DEFAULT_WAYU = {'f': 'f_young_clear', 'm': 'm_young_clear'}
MAX_CHARS = 90  # longer single chunks made Wayu misread words in a 2026-10-17 test (fine when said alone)
GAP_SECONDS = 0.25
SPEED_MIN, SPEED_MAX = 0.5, 2.0

MTL_MODEL = 'k2-fsa/OmniVoice'
MTL_STEPS = 16  # diffusion steps per chunk; OmniVoice's default is 32 (slower on CPU)
MTL_REF_TEXT = {'f': 'สวัสดีค่ะ ยินดีที่ได้รู้จัก วันนี้เรามาฟังเสียงภาษาไทยกัน',
                'm': 'สวัสดีครับ ยินดีที่ได้รู้จัก วันนี้เรามาฟังเสียงภาษาไทยกัน'}
MTL_INSTRUCT = {'f': 'female, young adult', 'm': 'male, young adult'}
MTL_SAMPLE_RATE = 24000


def is_edge_voice(voice):
    return bool(voice) and (voice in EDGE_VOICES or voice.startswith('th-TH-') or voice.endswith('Neural'))


def voice_gender(voice):
    """'f' or 'm' for a known voice; female for an unknown one."""
    if not voice:
        return 'f'
    if voice in EDGE_VOICES:
        return EDGE_VOICES[voice]
    if voice.startswith('m_'):
        return 'm'
    return 'f'


def polite_for(voice):
    """The sentence-final particle a voice should use: ค่ะ for a female voice, ครับ for a male one."""
    return 'ครับ' if voice_gender(voice) == 'm' else 'ค่ะ'


# ---------------------------------------------------------------------------------------------------------
# Thai numbers
# ---------------------------------------------------------------------------------------------------------

DIGITS = ['ศูนย์', 'หนึ่ง', 'สอง', 'สาม', 'สี่', 'ห้า', 'หก', 'เจ็ด', 'แปด', 'เก้า']
PLACES = ['', 'สิบ', 'ร้อย', 'พัน', 'หมื่น', 'แสน']
MAX_DIGITS = 15  # longer digit runs are read digit by digit (same limit in docs/tth.js)


def _group(s):
    """Words for a string of 1-6 digits, value 1..999999."""
    s = s.lstrip('0')
    out = ''
    n = len(s)
    for i, ch in enumerate(s):
        d = ord(ch) - 48
        p = n - 1 - i
        if d == 0:
            continue
        if p == 1 and d == 1:
            out += 'สิบ'
        elif p == 1 and d == 2:
            out += 'ยี่สิบ'
        elif p == 0 and d == 1 and n > 1:
            out += 'เอ็ด'
        else:
            out += DIGITS[d] + PLACES[p]
    return out


def read_digits(s):
    """Each digit on its own: '095' -> 'ศูนย์เก้าห้า'."""
    return ''.join(DIGITS[ord(c) - 48] for c in s)


def read_int(s):
    """Thai words for a non-negative integer written as digits: '8192' -> 'แปดพันหนึ่งร้อยเก้าสิบสอง'."""
    s = s.replace(',', '')
    if len(s) > MAX_DIGITS:
        return read_digits(s)
    s2 = s.lstrip('0')
    if not s2:
        return DIGITS[0]
    if len(s) - len(s2) > 0 and len(s) > 1:  # a leading zero (phone, code): read digit by digit
        return read_digits(s)
    out = ''
    while len(s2) > 6:
        head, s2 = s2[:-6], s2[-6:]
        out += read_int(head) + 'ล้าน'
        s2 = s2.lstrip('0')
        if not s2:
            return out
        if len(s2) <= 6:
            break
    return out + _group(s2)


def read_number(s):
    """'97.6' -> 'เก้าสิบเจ็ดจุดหก', '8,192' -> 'แปดพันหนึ่งร้อยเก้าสิบสอง'."""
    if '.' in s:
        a, b = s.split('.', 1)
        return read_int(a) + 'จุด' + read_digits(b)
    return read_int(s)


# ---------------------------------------------------------------------------------------------------------
# Text frontend (ported 1:1 to docs/tth.js; keep the two in step, eval/parity.py checks them)
# ---------------------------------------------------------------------------------------------------------

LETTERS = {'A': 'เอ', 'B': 'บี', 'C': 'ซี', 'D': 'ดี', 'E': 'อี', 'F': 'เอฟ', 'G': 'จี', 'H': 'เอช', 'I': 'ไอ',
           'J': 'เจ', 'K': 'เค', 'L': 'แอล', 'M': 'เอ็ม', 'N': 'เอ็น', 'O': 'โอ', 'P': 'พี', 'Q': 'คิว',
           'R': 'อาร์', 'S': 'เอส', 'T': 'ที', 'U': 'ยู', 'V': 'วี', 'W': 'ดับเบิลยู', 'X': 'เอ็กซ์', 'Y': 'วาย',
           'Z': 'แซด'}

# English names and terms with a fixed Thai reading, matched case-sensitively as whole ASCII words.
LEXICON = [
    ('TER-AI', 'เธอเอไอ'), ('TER AI', 'เธอเอไอ'), ('TER', 'เธอ'), ('TTH', 'ทีทีเอช'), ('TTS', 'ทีทีเอส'),
    ('CC BY-SA', 'ซีซี บายเอสเอ'), ('Wikipedia', 'วิกิพีเดีย'), ('GitHub', 'กิตฮับ'), ('Sesame', 'เซซามี'),
    ('SearXNG', 'เซิร์ชเอ็นจี'), ('Python', 'ไพทอน'), ('JavaScript', 'จาวาสคริปต์'), ('CPU', 'ซีพียู'),
    ('GPU', 'จีพียู'), ('AI', 'เอไอ'),
]

# Abbreviations (Thai text, so no ASCII boundaries needed); ม./ป. only before a number (ม.4 = มอสี่).
ABBREVIATIONS = [('พ.ศ.', 'พุทธศักราช'), ('ค.ศ.', 'คริสต์ศักราช'), ('กม.', 'กิโลเมตร'), ('ซม.', 'เซนติเมตร'),
                 ('มม.', 'มิลลิเมตร'), ('กก.', 'กิโลกรัม'), ('ชม.', 'ชั่วโมง'), ('ตร.', 'ตาราง'), ('ฯลฯ', 'และอื่น ๆ')]

SYMBOLS = [('×', ' คูณ '), ('÷', ' หาร '), ('=', ' เท่ากับ '), ('+', ' บวก '), ('−', ' ลบ '), ('√', ' รากที่สองของ '),
           ('^', ' ยกกำลัง '), ('°C', ' องศาเซลเซียส '), ('°F', ' องศาฟาเรนไฮต์ '), ('°', ' องศา '),
           ('&', ' และ '), ('%', 'เปอร์เซ็นต์ '), ('→', ' '), ('•', ' ')]

THAI = '\u0E00-\u0E7F'
_NON_BMP = re.compile('[\U00010000-\U0010FFFF\uFE0F\u200B-\u200D]')
_CITE = re.compile(r'\(ที่มา: ?([^,)]*)[^)]*\)')
_URL = re.compile(r'(?:https?://|www\.)[^\s)]+')
_THAI_DIGIT = re.compile('[\u0E50-\u0E59]')
_MO = re.compile('(?<![' + THAI + '])([มป])\\. ?(?=[0-9])')
_TIME = re.compile(r'(?<![0-9.:])([01]?[0-9]|2[0-3]):([0-5][0-9])(?![0-9])(?: ?น\.)?')
_VERSION = re.compile(r'(?<![0-9A-Za-z.])(v?)([0-9]+(?:\.[0-9]+){2,})(?![0-9])')
_TIMES = re.compile(r'([0-9]) ?\* ?(?=[0-9])')
_SLASH = re.compile(r'([0-9]) ?/ ?(?=[0-9])')
_MINUS = re.compile(r'([0-9]) - (?=[0-9])')
_NEG = re.compile('(?<![0-9A-Za-z' + THAI + '])-(?=[0-9])')
_NUMBER = re.compile(r'[0-9]{1,3}(?:,[0-9]{3})+(?:\.[0-9]+)?|[0-9]+(?:\.[0-9]+)?')
_ACRONYM = re.compile('(?<![A-Za-z])[A-Z]{2,6}(?![A-Za-z])')
_DROP = re.compile('["“”‘’\'«»()\\[\\]{}<>*_#|\\\\`~]')
_SPACES = re.compile('[ \t\u00A0]+')


def _word(term):
    return re.compile('(?<![A-Za-z0-9])' + re.escape(term) + '(?![A-Za-z0-9])')


_LEXICON = [(_word(a), b) for a, b in LEXICON]


def _time(m):
    h, mi = int(m.group(1)), int(m.group(2))
    out = ' ' + read_int(str(h)) + ' นาฬิกา'
    if mi:
        out += ' ' + read_int(str(mi)) + ' นาที'
    return out + ' '


def _version(m):
    words = 'จุด'.join(read_int(p) for p in m.group(2).split('.'))  # one word, so chunk() never splits it
    return (' เวอร์ชัน ' if m.group(1) else ' ') + words + ' '


def prepare(text, polite='ครับ'):
    """Rewrite a message the way it should be spoken. Returns lines joined by '\\n' (empty lines dropped).

    polite: 'ครับ' or 'ค่ะ'; replaces TER-AI's ครับ/ค่ะ and ครับ/คะ slashes.
    """
    if polite not in ('ครับ', 'ค่ะ'):
        raise ValueError("polite must be 'ครับ' or 'ค่ะ'")
    t = _NON_BMP.sub('', text or '')
    t = _CITE.sub(lambda m: ' ที่มา ' + m.group(1) + ' ', t)
    t = _URL.sub(' ', t)
    t = t.replace('[ค้นเว็บ]', 'จากการค้นเว็บ')
    p1, p2 = ('ครับ', 'ครับ') if polite == 'ครับ' else ('ค่ะ', 'คะ')
    t = t.replace('ครับ/ค่ะ', p1).replace('ค่ะ/ครับ', p1).replace('ครับ/คะ', p2).replace('คะ/ครับ', p2)
    t = _THAI_DIGIT.sub(lambda m: chr(ord(m.group(0)) - 0x0E50 + 48), t)
    for rx, rep in _LEXICON:
        t = rx.sub(rep, t)
    for a, b in ABBREVIATIONS:
        t = t.replace(a, b)
    t = _MO.sub(lambda m: ('มอ' if m.group(1) == 'ม' else 'ปอ'), t)
    t = _TIME.sub(_time, t)
    t = _VERSION.sub(_version, t)
    t = _TIMES.sub(r'\1 คูณ ', t)
    t = _SLASH.sub(r'\1 ทับ ', t)
    t = _MINUS.sub(r'\1 ลบ ', t)
    for a, b in SYMBOLS:
        t = t.replace(a, b)
    t = _NEG.sub('ลบ', t)
    t = _NUMBER.sub(lambda m: read_number(m.group(0)), t)
    t = _ACRONYM.sub(lambda m: ''.join(LETTERS[c] for c in m.group(0)), t)
    t = _DROP.sub(' ', t)
    t = t.replace(':', ' ').replace(';', ',')
    lines = []
    for line in t.split('\n'):
        line = _SPACES.sub(' ', line).strip()
        if line:
            lines.append(line)
    return '\n'.join(lines)


_COMBINING = set(chr(c) for c in [0x0E31] + list(range(0x0E34, 0x0E3B)) + list(range(0x0E47, 0x0E4F)))
_LEADING = set(chr(c) for c in range(0x0E40, 0x0E45))


def _hard_split(piece, max_chars):
    """Cut a piece with no spaces, never before a Thai combining mark or after a leading vowel."""
    out = []
    s = piece
    while len(s) > max_chars:
        cut = max_chars
        while cut > 1 and (s[cut] in _COMBINING or s[cut - 1] in _LEADING):
            cut -= 1
        out.append(s[:cut])
        s = s[cut:]
    if s:
        out.append(s)
    return out


def chunk(text, max_chars=MAX_CHARS):
    """Split prepared text into pieces of at most max_chars: at line breaks, then at spaces (Thai phrase gaps)."""
    if max_chars < 8:
        raise ValueError('max_chars must be at least 8')
    out = []
    for line in text.split('\n'):
        cur = ''
        for piece in line.split(' '):
            if not piece:
                continue
            parts = _hard_split(piece, max_chars) if len(piece) > max_chars else [piece]
            for p in parts:
                if cur and len(cur) + 1 + len(p) > max_chars:
                    out.append(cur)
                    cur = p
                else:
                    cur = cur + ' ' + p if cur else p
        if cur:
            out.append(cur)
    return out


# ---------------------------------------------------------------------------------------------------------
# Audio helpers
# ---------------------------------------------------------------------------------------------------------

class TTHError(RuntimeError):
    """Speech could not be made."""


class TTHUnavailable(TTHError):
    """No speech engine is installed."""


INSTALL_HINT = ('No TTH speech engine is installed. Local engine (Python 3.10+, downloads the Wayu weights from '
                'Hugging Face on first use): pip install "terai-router[tth] @ '
                'git+https://github.com/klanarongz2009-sketch/terai-router.git". Online fallback only: '
                'pip install edge-tts')


def _ffmpeg():
    exe = shutil.which('ffmpeg')
    if not exe:
        raise TTHError('ffmpeg is needed to convert between WAV and MP3; install ffmpeg or change the output '
                       'extension')
    return exe


def _convert(src, dst):
    r = subprocess.run([_ffmpeg(), '-y', '-loglevel', 'error', '-i', src] +
                       (['-codec:a', 'libmp3lame', '-q:a', '2'] if dst.lower().endswith('.mp3') else ['-ac', '1']) +
                       [dst], capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(dst) or os.path.getsize(dst) == 0:
        raise TTHError('ffmpeg conversion failed: ' + r.stderr.strip()[-300:])


def write_wav(path, samples, sample_rate):
    """Write mono float samples (-1..1, any sequence or numpy array) as 16-bit PCM WAV."""
    import array
    import wave
    try:
        import numpy as np
        pcm = (np.clip(np.asarray(samples, dtype='float32'), -1.0, 1.0) * 32767.0).astype('<i2').tobytes()
    except ImportError:
        a = array.array('h', (int(max(-1.0, min(1.0, float(x))) * 32767.0) for x in samples))
        pcm = a.tobytes()
    with wave.open(path, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(int(sample_rate))
        w.writeframes(pcm)


def duration(path):
    """Length of an audio file in seconds (WAV natively, anything else with ffprobe), or None."""
    if path.lower().endswith('.wav'):
        import wave
        try:
            with wave.open(path, 'rb') as w:
                return w.getnframes() / float(w.getframerate())
        except (wave.Error, EOFError, OSError):
            pass
    exe = shutil.which('ffprobe')
    if not exe:
        return None
    r = subprocess.run([exe, '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=nw=1:nk=1', path],
                       capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return None


# ---------------------------------------------------------------------------------------------------------
# Engines
# ---------------------------------------------------------------------------------------------------------

class WayuEngine:
    """Local Wayu-Paxa-TTS-Edge (open weights by Paxa Labs / Wayu Research, CC-BY-NC-4.0, non-commercial).

    The `wayu_tts` package is optional (extra `tth`); the weights are fetched from Hugging Face by
    `ThaiTTS.from_pretrained` on first use and cached there (about 315 MB: model.pth is 313 MB), never stored in this repository.
    """
    name = 'wayu'
    online = False
    output = '.wav'

    def __init__(self, model=WAYU_MODEL, device=None):
        self.model = model
        self.device = device
        self._tts = None

    @staticmethod
    def available():
        return importlib.util.find_spec('wayu_tts') is not None

    def voice_for(self, voice):
        if voice in WAYU_VOICES:
            return voice
        return DEFAULT_WAYU[voice_gender(voice)]

    def load(self):
        if self._tts is None:
            import contextlib
            import logging
            import sys
            import warnings
            # kokoro print()s a repo_id warning on stdout; keep stdout clean for --json and chat transcripts
            with warnings.catch_warnings(), contextlib.redirect_stdout(sys.stderr):
                warnings.simplefilter('ignore')
                logging.getLogger('phonemizer').setLevel(logging.ERROR)
                try:  # kokoro logs a repo_id warning through loguru on every load
                    from loguru import logger
                    logger.disable('kokoro')
                except ImportError:
                    pass
                from wayu_tts import ThaiTTS
                self._tts = ThaiTTS.from_pretrained(self.model, device=self.device)
        return self._tts

    def synthesize(self, chunks, voice, speed, seed, out):
        import numpy as np
        import warnings
        tts = self.load()
        gap = np.zeros(int(GAP_SECONDS * tts.sample_rate), dtype=np.float32)
        clips = []
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            for i, piece in enumerate(chunks):
                if clips:
                    clips.append(gap)
                clips.append(np.asarray(tts(piece, voice=voice, speed=speed, seed=seed + i), dtype=np.float32))
        audio = np.concatenate(clips) if clips else np.zeros(0, dtype=np.float32)
        if audio.size == 0:
            raise TTHError('wayu produced no audio')
        if out.lower().endswith('.wav'):
            write_wav(out, audio, tts.sample_rate)
        else:
            with tempfile.TemporaryDirectory() as d:
                wav = os.path.join(d, 'tth.wav')
                write_wav(wav, audio, tts.sample_rate)
                _convert(wav, out)


class EdgeEngine:
    """edge-tts: the online Microsoft Edge read-aloud service. The text is sent to Microsoft."""
    name = 'edge'
    online = True
    output = '.mp3'

    @staticmethod
    def available():
        return importlib.util.find_spec('edge_tts') is not None

    def voice_for(self, voice):
        if is_edge_voice(voice):
            return voice
        return DEFAULT_EDGE[voice_gender(voice)]

    def synthesize(self, chunks, voice, speed, seed, out):
        import asyncio
        import edge_tts
        rate = '%+d%%' % int(round((speed - 1.0) * 100))
        text = '\n'.join(chunks)

        async def run(path):
            await edge_tts.Communicate(text, voice, rate=rate).save(path)

        if out.lower().endswith('.mp3'):
            asyncio.run(run(out))
        else:
            with tempfile.TemporaryDirectory() as d:
                mp3 = os.path.join(d, 'tth.mp3')
                asyncio.run(run(mp3))
                _convert(mp3, out)
        if not os.path.exists(out) or os.path.getsize(out) == 0:
            raise TTHError('edge-tts produced no audio')


class MtlEngine:
    """TTH-MTL: local OmniVoice (k2-fsa, https://github.com/k2-fsa/OmniVoice), multilingual zero-shot TTS.

    Code Apache-2.0; weights CC-BY-NC (non-commercial). The `omnivoice` package is optional (extra `tth-mtl`);
    `OmniVoice.from_pretrained` downloads the weights from Hugging Face on first use (about 3.3 GB:
    model.safetensors 2.45 GB + audio_tokenizer 0.81 GB) and caches them there, never in this repository.

    Voice: for Thai, a Wayu voice name selects which Wayu voice reads the short Thai reference clip that OmniVoice
    clones (rendered once and cached in ~/.cache/terai/tth-mtl). With `ref_audio` (+ `ref_text`) it clones your
    own clip instead. Other languages, or Thai without Wayu, get a voice designed from the gender (`MTL_INSTRUCT`).
    """
    name = 'mtl'
    online = False
    output = '.wav'

    def __init__(self, model=MTL_MODEL, lang='th', ref_audio=None, ref_text=None, num_step=MTL_STEPS,
                 cache_dir=None, wayu=None):
        self.model = model
        self.lang = lang
        self.ref_audio = ref_audio
        self.ref_text = ref_text
        self.num_step = int(num_step)
        self.cache_dir = cache_dir or os.path.join(os.path.expanduser('~'), '.cache', 'terai', 'tth-mtl')
        self.wayu = wayu
        self._ov = None
        self._prompts = {}

    @staticmethod
    def available():
        return importlib.util.find_spec('omnivoice') is not None

    def voice_for(self, voice):
        if voice in WAYU_VOICES:
            return voice
        return DEFAULT_WAYU[voice_gender(voice)]

    def load(self):
        if self._ov is None:
            import contextlib
            import logging
            import sys
            import warnings
            with warnings.catch_warnings(), contextlib.redirect_stdout(sys.stderr):
                warnings.simplefilter('ignore')
                logging.getLogger('omnivoice').setLevel(logging.ERROR)
                from omnivoice import OmniVoice
                try:
                    import torch
                    dtype = torch.float32  # bfloat16/float16 are slower or unsupported on most CPUs
                except ImportError:
                    dtype = None
                self._ov = OmniVoice.from_pretrained(self.model, device_map='cpu', dtype=dtype)
        return self._ov

    def reference(self, voice):
        """(audio path, transcript) of the clip to clone, or None to design a voice from its gender."""
        if self.ref_audio:
            return self.ref_audio, self.ref_text
        if self.lang != 'th':  # a Thai reference clip would give other languages a Thai accent
            return None
        wayu = self.wayu if self.wayu is not None else WayuEngine()
        if not wayu.available():
            return None
        text = MTL_REF_TEXT[voice_gender(voice)]
        path = os.path.join(self.cache_dir, 'ref-%s.wav' % voice)
        if not os.path.exists(path) or os.path.getsize(path) == 0:
            os.makedirs(self.cache_dir, exist_ok=True)
            tmp = path + '.tmp.wav'
            wayu.synthesize([text], voice, 1.0, 0, tmp)
            os.replace(tmp, path)
        return path, text

    def _prompt_kwargs(self, voice):
        if voice not in self._prompts:
            ref = self.reference(voice)
            if ref is None:
                self._prompts[voice] = {'instruct': MTL_INSTRUCT[voice_gender(voice)]}
            else:
                prompt = self.load().create_voice_clone_prompt(ref_audio=ref[0], ref_text=ref[1])
                self._prompts[voice] = {'voice_clone_prompt': prompt}
        return self._prompts[voice]

    def synthesize(self, chunks, voice, speed, seed, out):
        import warnings
        import numpy as np
        from omnivoice.models.omnivoice import OmniVoiceGenerationConfig
        try:
            import torch
        except ImportError:  # only used for the sampling seed
            torch = None
        model = self.load()
        kw = self._prompt_kwargs(voice)
        cfg = OmniVoiceGenerationConfig(num_step=self.num_step)
        sr = int(getattr(model, 'sampling_rate', MTL_SAMPLE_RATE) or MTL_SAMPLE_RATE)
        gap = np.zeros(int(GAP_SECONDS * sr), dtype=np.float32)
        clips = []
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            for i, piece in enumerate(chunks):
                if torch is not None:
                    torch.manual_seed(seed + i)
                extra = {'speed': speed} if speed != 1.0 else {}
                audio = model.generate(text=piece, language=self.lang, generation_config=cfg, **kw, **extra)[0]
                if clips:
                    clips.append(gap)
                clips.append(np.asarray(audio, dtype=np.float32).reshape(-1))
        audio = np.concatenate(clips) if clips else np.zeros(0, dtype=np.float32)
        if audio.size == 0:
            raise TTHError('mtl produced no audio')
        if out.lower().endswith('.wav'):
            write_wav(out, audio, sr)
        else:
            with tempfile.TemporaryDirectory() as d:
                wav = os.path.join(d, 'tth.wav')
                write_wav(wav, audio, sr)
                _convert(wav, out)


ENGINES = ('wayu', 'edge', 'mtl')
FALLBACK_ENGINES = ('wayu', 'edge')  # Thai engines tried after the first one fails; mtl is opt-in only


class TTH:
    """Thai speech for TER-AI.

        TTH().synthesize('สวัสดีครับ/ค่ะ', 'hello.wav')
        TTH(engine='edge', voice='th-TH-NiwatNeural', speed=1.1).synthesize(text, 'out.mp3')

    engine: 'auto' (Wayu if installed, then edge-tts), 'wayu', 'edge' or 'mtl' (TTH-MTL, OmniVoice; opt-in).
    voice: a Wayu voice (f_young_clear, m_young_clear, ...) or an edge-tts voice (th-TH-PremwadeeNeural, ...).
           When an engine cannot use the voice, it takes its own voice of the same gender.
    fallback: when the first engine is missing or fails, try the other one.
    polite: 'ครับ' or 'ค่ะ' for TER-AI's ครับ/ค่ะ slash; by default it follows the voice's gender.
    lang: 'th' (default). Any other OmniVoice language code ('en', 'ja', 'lo', ...) needs engine='mtl'; the text
          is then spoken as written (no Thai frontend) and there is no fallback, since Wayu and edge read Thai.
    ref_audio / ref_text: a clip (and its transcript) for TTH-MTL to clone instead of the Wayu reference voice.
    """

    def __init__(self, engine='auto', voice=None, speed=1.0, polite=None, fallback=True, max_chars=MAX_CHARS,
                 seed=0, engines=None, lang='th', ref_audio=None, ref_text=None, mtl_steps=MTL_STEPS):
        if engine not in ('auto',) + ENGINES:
            raise ValueError('engine must be auto, wayu, edge or mtl')
        lang = (lang or 'th').strip()
        if lang != 'th' and engine != 'mtl':
            raise ValueError('lang %r needs engine mtl (TTH-MTL); wayu and edge speak Thai only' % lang)
        if ref_audio is not None and not os.path.exists(ref_audio):
            raise ValueError('ref_audio not found: %s' % ref_audio)
        if int(mtl_steps) < 1:
            raise ValueError('mtl_steps must be at least 1')
        speed = float(speed)
        if not SPEED_MIN <= speed <= SPEED_MAX:
            raise ValueError('speed must be between %.1f and %.1f' % (SPEED_MIN, SPEED_MAX))
        if voice is not None and not (voice in WAYU_VOICES or is_edge_voice(voice)):
            raise ValueError('unknown voice %r; Wayu voices: %s; edge-tts voices: %s'
                             % (voice, ', '.join(WAYU_VOICES), ', '.join(EDGE_VOICES)))
        self.engine = engine
        self.voice = voice or DEFAULT_VOICE
        self.speed = speed
        self.polite = polite or polite_for(self.voice)
        self.fallback = fallback
        self.max_chars = max_chars
        self.seed = seed
        self.lang = lang
        if engines is None:
            wayu = WayuEngine()
            engines = {'wayu': wayu, 'edge': EdgeEngine(),
                       'mtl': MtlEngine(lang=lang, ref_audio=ref_audio, ref_text=ref_text, num_step=mtl_steps,
                                        wayu=wayu)}
        self.engines = engines

    def order(self):
        """Engine names to try, in order."""
        if self.engine == 'auto':
            first = 'edge' if is_edge_voice(self.voice) else 'wayu'
        else:
            first = self.engine
        if self.lang != 'th':
            return [first]
        rest = [e for e in FALLBACK_ENGINES if e != first]
        return [first] + (rest if self.fallback else [])

    def plan(self, text):
        """The spoken text and its chunks, without making audio."""
        if self.lang != 'th':  # TTH-MTL in another language: speak the text as written
            spoken = re.sub(r'[ \t]+', ' ', text).strip()
            return spoken, chunk(spoken, self.max_chars)
        spoken = prepare(text, self.polite)
        return spoken, chunk(spoken, self.max_chars)

    def synthesize(self, text, out):
        """Write speech for `text` to `out` (.wav or .mp3). Returns a dict describing what was done."""
        ext = os.path.splitext(out)[1].lower()
        if ext not in ('.wav', '.mp3'):
            raise ValueError('output must end in .wav or .mp3')
        spoken, pieces = self.plan(text)
        if not pieces:
            raise ValueError('nothing to say: the text is empty after preparation')
        errors = []
        tried = 0
        for name in self.order():
            eng = self.engines.get(name)
            if eng is None or not eng.available():
                errors.append(name + ': not installed')
                continue
            tried += 1
            voice = eng.voice_for(self.voice)
            try:
                eng.synthesize(pieces, voice, self.speed, self.seed, out)
            except Exception as e:  # engine failed (offline, download error, ...): try the next one
                errors.append('%s: %s: %s' % (name, type(e).__name__, str(e)[:300]))
                continue
            return {'out': out, 'engine': name, 'voice': voice, 'online': bool(getattr(eng, 'online', False)),
                    'fallback_used': name != self.order()[0], 'chunks': len(pieces), 'text': spoken,
                    'seconds': duration(out), 'errors': errors}
        if not tried:
            raise TTHUnavailable(INSTALL_HINT + ' (' + '; '.join(errors) + ')')
        raise TTHError('every engine failed: ' + '; '.join(errors))


def speak(text, out, **kw):
    """Shortcut: TTH(**kw).synthesize(text, out)."""
    return TTH(**kw).synthesize(text, out)


def installed_engines():
    return {'wayu': WayuEngine.available(), 'edge': EdgeEngine.available(), 'mtl': MtlEngine.available()}


PLAYERS = [['ffplay', '-nodisp', '-autoexit', '-loglevel', 'quiet'], ['paplay'], ['aplay', '-q'], ['afplay'],
           ['mpv', '--no-video', '--really-quiet'], ['termux-media-player', 'play']]


def find_player():
    """A command that plays an audio file on this machine, or None."""
    for cmd in PLAYERS:
        if shutil.which(cmd[0]):
            return cmd
    return None
