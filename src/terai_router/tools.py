"""Deterministic tools used by Chat: calculator, dates, unit conversion, random numbers, text ops.

Everything here is pure Python with integer or IEEE-754 arithmetic only (+ - * / sqrt), so the
JavaScript port in docs/chat.js returns the same strings for the same input, clock and seed.
"""
import math
import re

# ---------------------------------------------------------------- number formatting

def fmt_num(x, places=6):
    """Round half up at `places` decimals (same formula as JS Math.round) and print briefly."""
    if x != x or x in (float('inf'), float('-inf')):
        return str(x)
    p = 10 ** places
    r = math.floor(x * p + 0.5) / p
    if r == 0:
        r = 0.0
    if r == int(r) and abs(r) < 1e15:
        return str(int(r))
    s = repr(r)
    if 'e' in s or 'E' in s:
        return s
    return s


# ---------------------------------------------------------------- calculator (no eval)

class CalcError(Exception):
    pass


_WORD_OPS = [
    ('ยกกำลัง', '^'), ('คูณด้วย', '*'), ('หารด้วย', '/'), ('บวก', '+'), ('ลบ', '-'), ('คูณ', '*'), ('หาร', '/'),
    ('×', '*'), ('÷', '/'), ('plus', '+'), ('minus', '-'), ('times', '*'), ('divided by', '/'),
]
_SQRT = re.compile(r'(?:รากที่สอง(?:ของ)?|สแควร์รูท|sqrt|√) ?\(?([0-9.]+)\)?')
_PCT_OF = re.compile(r'([0-9.]+) ?(?:%|เปอร์เซ็นต์) ?(?:ของ|of) ?([0-9.]+)')
_EXPR = re.compile(r'[0-9.()+\-*/^ ]+')


def calc_prepare(text):
    """Thai/English math words -> symbols. Returns the longest arithmetic span, or None."""
    t = text.lower().replace(',', '')
    t = _PCT_OF.sub(lambda m: '(' + m.group(1) + '/100*' + m.group(2) + ')', t)
    t = _SQRT.sub(lambda m: 's' + m.group(1), t)
    for w, s in _WORD_OPS:
        t = t.replace(w, ' ' + s + ' ')
    t = re.sub(r' +', ' ', t)
    t = re.sub(r'(?<=[0-9)]) ?x ?(?=[0-9(])', '*', t)
    best = None
    for m in re.finditer(r'[0-9.()+\-*/^ s]+', t):
        span = m.group(0).strip()
        if not re.search(r'[0-9]', span):
            continue
        if not (re.search(r'[0-9)] ?[+\-*/^] ?[-(s0-9]', span) or 's' in span):
            continue
        if best is None or len(span) > len(best):
            best = span
    return best


def _tokens(expr):
    out, i = [], 0
    while i < len(expr):
        c = expr[i]
        if c == ' ':
            i += 1
        elif c in '0123456789.':
            j = i
            while j < len(expr) and expr[j] in '0123456789.':
                j += 1
            num = expr[i:j]
            if num.count('.') > 1 or num == '.':
                raise CalcError('bad number')
            out.append(float(num))
            i = j
        elif c in '+-*/^()s':
            out.append(c)
            i += 1
        else:
            raise CalcError('bad char')
    return out


def calc_eval(expr):
    """Recursive-descent parser: + - * / ^ ( ) unary minus, s = sqrt. Raises CalcError."""
    toks = _tokens(expr)
    pos = [0]

    def peek():
        return toks[pos[0]] if pos[0] < len(toks) else None

    def take():
        pos[0] += 1
        return toks[pos[0] - 1]

    def atom():
        t = peek()
        if t is None:
            raise CalcError('incomplete')
        if t == '-':
            take()
            return -atom()
        if t == '+':
            take()
            return atom()
        if t == 's':
            take()
            v = atom()
            if v < 0:
                raise CalcError('sqrt of negative')
            return math.sqrt(v)
        if t == '(':
            take()
            v = add()
            if peek() != ')':
                raise CalcError('missing )')
            take()
            return v
        if isinstance(t, float):
            take()
            return t
        raise CalcError('unexpected ' + str(t))

    def power():
        b = atom()
        if peek() == '^':
            take()
            e = power()
            if e == int(e) and abs(e) <= 1024:
                r, k = 1.0, int(abs(e))
                for _ in range(k):
                    r *= b
                if e < 0:
                    if r == 0:
                        raise CalcError('div0')
                    r = 1.0 / r
                return r
            raise CalcError('non-integer power')
        return b

    def mul():
        v = power()
        while peek() in ('*', '/'):
            op = take()
            r = power()
            if op == '*':
                v *= r
            else:
                if r == 0:
                    raise CalcError('div0')
                v /= r
        return v

    def add():
        v = mul()
        while peek() in ('+', '-'):
            op = take()
            r = mul()
            v = v + r if op == '+' else v - r
        return v

    v = add()
    if pos[0] != len(toks):
        raise CalcError('trailing')
    if abs(v) > 1e300:
        raise CalcError('overflow')
    return v


def pretty_expr(expr):
    e = expr.replace('s', '√').replace('*', ' × ').replace('/', ' ÷ ').replace('+', ' + ').replace('^', ' ^ ')
    e = re.sub(r'(?<=[0-9)]) ?- ?', ' - ', e)
    return re.sub(r' +', ' ', e).strip()


# ---------------------------------------------------------------- dates (civil calendar, no time zones)

TH_DAYS = ['จันทร์', 'อังคาร', 'พุธ', 'พฤหัสบดี', 'ศุกร์', 'เสาร์', 'อาทิตย์']
TH_MONTHS = ['มกราคม', 'กุมภาพันธ์', 'มีนาคม', 'เมษายน', 'พฤษภาคม', 'มิถุนายน', 'กรกฎาคม', 'สิงหาคม', 'กันยายน', 'ตุลาคม', 'พฤศจิกายน', 'ธันวาคม']


def days_from_civil(y, m, d):
    y -= m <= 2
    era = (y if y >= 0 else y - 399) // 400
    yoe = y - era * 400
    doy = (153 * (m + (-3 if m > 2 else 9)) + 2) // 5 + d - 1
    doe = yoe * 365 + yoe // 4 - yoe // 100 + doy
    return era * 146097 + doe - 719468


def civil_from_days(z):
    z += 719468
    era = (z if z >= 0 else z - 146096) // 146097
    doe = z - era * 146097
    yoe = (doe - doe // 1460 + doe // 36524 - doe // 146096) // 365
    y = yoe + era * 400
    doy = doe - (365 * yoe + yoe // 4 - yoe // 100)
    mp = (5 * doy + 2) // 153
    d = doy - (153 * mp + 2) // 5 + 1
    m = mp + (3 if mp < 10 else -9)
    return y + (m <= 2), m, d


def weekday(z):
    """0 = Monday for a day number from days_from_civil (1970-01-01 was a Thursday)."""
    return (z + 3) % 7


def th_date(z, with_day=True):
    y, m, d = civil_from_days(z)
    s = f'{d} {TH_MONTHS[m - 1]} {y + 543}'
    return ('วัน' + TH_DAYS[weekday(z)] + 'ที่ ' + s) if with_day else s


# ---------------------------------------------------------------- unit conversion

# name -> (dimension, factor to base unit). temperature handled separately.
UNITS = [
    (('กิโลเมตร', 'กม.', 'กม', 'km', 'kilometers', 'kilometer'), 'len', 1000.0, 'กิโลเมตร'),
    (('เซนติเมตร', 'ซม.', 'ซม', 'cm'), 'len', 0.01, 'เซนติเมตร'),
    (('มิลลิเมตร', 'มม.', 'mm'), 'len', 0.001, 'มิลลิเมตร'),
    (('เมตร', 'meters', 'meter', 'm'), 'len', 1.0, 'เมตร'),
    (('ไมล์', 'miles', 'mile', 'mi'), 'len', 1609.344, 'ไมล์'),
    (('นิ้ว', 'inches', 'inch', 'in'), 'len', 0.0254, 'นิ้ว'),
    (('ฟุต', 'feet', 'foot', 'ft'), 'len', 0.3048, 'ฟุต'),
    (('หลา', 'yards', 'yard', 'yd'), 'len', 0.9144, 'หลา'),
    (('กิโลกรัม', 'กก.', 'กก', 'กิโล', 'kg', 'kilograms', 'kilogram'), 'mass', 1000.0, 'กิโลกรัม'),
    (('กรัม', 'grams', 'gram', 'g'), 'mass', 1.0, 'กรัม'),
    (('ปอนด์', 'pounds', 'pound', 'lb', 'lbs'), 'mass', 453.59237, 'ปอนด์'),
    (('ออนซ์', 'ounces', 'ounce', 'oz'), 'mass', 28.349523125, 'ออนซ์'),
    (('ตัน', 'tonnes', 'tonne', 'tons', 'ton'), 'mass', 1000000.0, 'ตัน'),
    (('มิลลิลิตร', 'มล.', 'ml'), 'vol', 0.001, 'มิลลิลิตร'),
    (('ลิตร', 'liters', 'liter', 'litres', 'litre', 'l'), 'vol', 1.0, 'ลิตร'),
    (('แกลลอน', 'gallons', 'gallon', 'gal'), 'vol', 3.785411784, 'แกลลอน'),
    (('วินาที', 'seconds', 'second', 'sec', 's'), 'time', 1.0, 'วินาที'),
    (('นาที', 'minutes', 'minute', 'min'), 'time', 60.0, 'นาที'),
    (('ชั่วโมง', 'ชม.', 'hours', 'hour', 'hr', 'h'), 'time', 3600.0, 'ชั่วโมง'),
    (('สัปดาห์', 'อาทิตย์', 'weeks', 'week'), 'time', 604800.0, 'สัปดาห์'),
    (('วัน', 'days', 'day'), 'time', 86400.0, 'วัน'),
    (('องศาเซลเซียส', 'เซลเซียส', 'องศาซี', 'celsius', '°c'), 'temp', 'C', 'องศาเซลเซียส'),
    (('องศาฟาเรนไฮต์', 'ฟาเรนไฮต์', 'fahrenheit', '°f'), 'temp', 'F', 'องศาฟาเรนไฮต์'),
    (('เคลวิน', 'kelvin'), 'temp', 'K', 'เคลวิน'),
]
_ALIASES = sorted(((a, i) for i, u in enumerate(UNITS) for a in u[0]), key=lambda p: -len(p[0]))
_ASCII = re.compile(r'[a-z°]')


def find_units(t):
    """All unit mentions in order: [(start, end, unit_index)], longest alias wins, ASCII aliases need word edges."""
    taken = [False] * len(t)
    found = []
    for alias, idx in _ALIASES:
        start = 0
        while True:
            j = t.find(alias, start)
            if j < 0:
                break
            end = j + len(alias)
            ok = not any(taken[j:end])
            if ok and _ASCII.match(alias[0]):
                before = t[j - 1] if j > 0 else ' '
                after = t[end] if end < len(t) else ' '
                ok = not (before.isascii() and before.isalpha()) and not (after.isascii() and after.isalpha())
            if ok:
                for k in range(j, end):
                    taken[k] = True
                found.append((j, end, idx))
            start = end
    return sorted(found)


def to_base(v, u):
    dim, f = UNITS[u][1], UNITS[u][2]
    if dim != 'temp':
        return v * f
    if f == 'C':
        return v
    if f == 'F':
        return (v - 32) * 5 / 9
    return v - 273.15


def from_base(v, u):
    dim, f = UNITS[u][1], UNITS[u][2]
    if dim != 'temp':
        return v / f
    if f == 'C':
        return v
    if f == 'F':
        return v * 9 / 5 + 32
    return v + 273.15


def convert(v, a, b):
    if UNITS[a][1] != UNITS[b][1]:
        return None
    return from_base(to_base(v, a), b)


# ---------------------------------------------------------------- random (mulberry32, same as JS)

def rng_next(state):
    """-> (new_state, float in [0, 1)). 32-bit integer arithmetic only."""
    state = (state + 0x6D2B79F5) & 0xFFFFFFFF
    t = state
    t = ((t ^ (t >> 15)) * (t | 1)) & 0xFFFFFFFF
    t ^= (t + (((t ^ (t >> 7)) * (t | 61)) & 0xFFFFFFFF)) & 0xFFFFFFFF
    t &= 0xFFFFFFFF
    return state, ((t ^ (t >> 14)) & 0xFFFFFFFF) / 4294967296
