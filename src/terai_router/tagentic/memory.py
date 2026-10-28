"""The four Tagentic1 memory files, loaded every run in this order:

1. ``User.md``         who the user is (personal; in the memory folder only)
2. ``Systemprompt.md`` the prompt instructions Tagentic1 runs on (ships with the package)
3. ``Memory.md``       permanent memory (personal; the ``remember`` tool appends durable facts)
4. ``Systemskill.md``  system skills (ships with the package; includes the ai-memory-continuity skill)

The memory folder is ``$TERAI_TAGENTIC_HOME`` or ``~/.terai/tagentic``. ``User.md`` and ``Memory.md`` are created
there on first run and are never part of the repository. A ``Systemprompt.md`` or ``Systemskill.md`` placed in the
memory folder overrides the shipped one. Identity is set by Systemprompt.md only: there is no rule added by code and
no filter on the replies, so an edited ``Systemprompt.md`` changes it.
"""
from __future__ import annotations

import datetime as _dt
import os
import re
from dataclasses import dataclass
from pathlib import Path

MEMORY_ORDER = ('User.md', 'Systemprompt.md', 'Memory.md', 'Systemskill.md')
PERSONAL = ('User.md', 'Memory.md')
SHIPPED = ('Systemprompt.md', 'Systemskill.md')
DATA_DIR = Path(__file__).resolve().parent / 'data'
SKILLS_DIR = DATA_DIR / 'skills'
INCLUDE = re.compile(r'^<!--\s*include\s+(skills/[A-Za-z0-9_.\-/]+)\s*-->\s*$', re.M)

# Characters kept from each file in the prompt (the rest is cut and marked). Memory.md keeps its newest lines.
LIMITS = {'User.md': 3000, 'Systemprompt.md': 8000, 'Memory.md': 4000, 'Systemskill.md': 9000}

USER_STARTER = (
    '# User.md\n\n'
    'Who the user is, for Tagentic1. Write it yourself: the name to use, languages, how you like answers, the\n'
    'projects you work on. Tagentic1 reads this file at the start of every run. It adds lines under\n'
    '"## Profile" only through its remember tool (file=User.md), after you confirm.\n'
    'Do not put passwords, API keys, tokens or other secrets here.\n'
)
MEMORY_STARTER = (
    '# Memory.md\n\n'
    'Permanent memory of Tagentic1. One durable fact per line, with its date. Tagentic1 adds lines with the\n'
    '`remember` tool (after you confirm); you can edit or delete lines yourself. No secrets, no raw transcripts.\n\n'
)


class MemoryRejected(ValueError):
    """A fact the remember tool refuses to store."""


@dataclass
class MemoryFile:
    name: str
    path: str      # where it was read from
    source: str    # user | package | override
    text: str


def default_home() -> Path:
    return Path(os.environ.get('TERAI_TAGENTIC_HOME') or os.path.join('~', '.terai', 'tagentic')).expanduser()


def init_home(home: str | os.PathLike | None = None) -> list:
    """Create the memory folder with User.md and Memory.md when they are missing. Returns the files created."""
    h = Path(home).expanduser() if home else default_home()
    h.mkdir(parents=True, exist_ok=True)
    made = []
    for name, text in (('User.md', USER_STARTER), ('Memory.md', MEMORY_STARTER)):
        p = h / name
        if not p.exists():
            p.write_text(text, encoding='utf-8')
            made.append(str(p))
    return made


def expand_includes(text: str) -> str:
    """Replace ``<!-- include skills/... -->`` lines with the vendored file (only files under data/skills)."""
    def sub(m):
        rel = m.group(1)
        p = (DATA_DIR / rel).resolve()
        if '..' in rel.split('/') or SKILLS_DIR.resolve() not in p.parents or not p.is_file():
            return f'(include not found: {rel})'
        return p.read_text(encoding='utf-8').strip()
    return INCLUDE.sub(sub, text)


def _cut(name: str, text: str) -> str:
    limit = LIMITS.get(name, 4000)
    if len(text) <= limit:
        return text
    if name == 'Memory.md':  # keep the newest facts
        return '(older lines cut)\n' + text[-limit:]
    return text[:limit] + '\n(cut)'


def load_memory(home: str | os.PathLike | None = None, create: bool = True) -> list:
    """Read the four files in MEMORY_ORDER. Returns a list of MemoryFile."""
    h = Path(home).expanduser() if home else default_home()
    if create:
        init_home(h)
    out = []
    for name in MEMORY_ORDER:
        if name in PERSONAL:
            p, source = h / name, 'user'
            text = p.read_text(encoding='utf-8') if p.is_file() else ''
        else:
            p, source = h / name, 'override'
            if not p.is_file():
                p, source = DATA_DIR / name, 'package'
            text = p.read_text(encoding='utf-8')
            if name == 'Systemskill.md':
                text = expand_includes(text)
        out.append(MemoryFile(name, str(p), source, _cut(name, text.strip())))
    return out


def system_text(files: list) -> str:
    return '\n\n'.join(f'===== {f.name} =====\n{f.text or "(empty)"}' for f in files)


# ---------------------------------------------------------------------------------------------- remember
SECRET = re.compile(
    r'(?:password|passwd|passphrase|รหัสผ่าน|api[ _-]?key|secret|token|otp|รหัส\s*otp|private\s+key)\s*(?:[:=：]|คือ|is)\s*\S|'
    r'\bsk-[A-Za-z0-9_-]{16,}|\bgh[pousr]_[A-Za-z0-9]{20,}|\bgithub_pat_[A-Za-z0-9_]{20,}|\bAKIA[0-9A-Z]{16}\b|'
    r'\bxox[abpr]-[A-Za-z0-9-]{10,}|-----BEGIN [A-Z ]*PRIVATE KEY-----|\bhf_[A-Za-z0-9]{20,}|'
    r'\b[A-Fa-f0-9]{32,}\b|\b[A-Za-z0-9+/]{40,}={0,2}',
    re.I)
PHONE = re.compile(r'(?<!\d)(?:\+?66[- ]?|0)[689]\d(?:[- ]?\d){7}(?!\d)')
CARD = re.compile(r'(?<!\d)(?:\d[ -]?){13,19}(?!\d)')
TRANSCRIPT = re.compile(r'^\s*(?:user|assistant|system|human|ai|bot|ผู้ใช้|tagentic1?|terai1?)\s*[:：>]', re.I | re.M)
FACT_MAX = 300


def check_fact(fact: str) -> str:
    """Return the cleaned fact, or raise MemoryRejected with the reason."""
    f = (fact or '').strip()
    if not f:
        raise MemoryRejected('empty fact')
    if len(f) > FACT_MAX or f.count('\n') >= 3:
        raise MemoryRejected(f'too long for one durable fact (max {FACT_MAX} characters, 3 lines); '
                             'save a short summary, not a transcript')
    if TRANSCRIPT.search(f):
        raise MemoryRejected('looks like a raw transcript; save the durable fact only')
    if SECRET.search(f):
        raise MemoryRejected('looks like a secret (password, key or token); secrets are never stored')
    if PHONE.search(f) or CARD.search(f):
        raise MemoryRejected('looks like a phone or card number; personal numbers are never stored')
    return ' '.join(f.split())


MEMORY_TARGETS = ('Memory.md', 'User.md')
KEYED = re.compile(r'^([^:\n]{1,24}):\s*\S')   # "ชื่อ: ...", "Occupation: ..." -> one line per key in User.md


def append_fact(home: str | os.PathLike | None, fact: str, today: str | None = None,
                target: str = 'Memory.md') -> tuple:
    """Add one fact. Memory.md: a dated line at the end. User.md: a line under "## Profile"; a fact written as
    "key: value" replaces the line with the same key. Returns (changed: bool, line)."""
    if target not in MEMORY_TARGETS:
        raise MemoryRejected(f'file must be one of {", ".join(MEMORY_TARGETS)}')
    clean = check_fact(fact)
    h = Path(home).expanduser() if home else default_home()
    init_home(h)
    p = h / target
    text = p.read_text(encoding='utf-8')
    if target == 'User.md':
        line = f'- {clean}'
        lines = text.splitlines()
        if any(x.strip() == line for x in lines):
            return False, line
        k = KEYED.match(clean)
        if k:
            key = k.group(1).strip().lower()
            for i, x in enumerate(lines):
                m = KEYED.match(x.lstrip('- ').strip())
                if x.startswith('- ') and m and m.group(1).strip().lower() == key:
                    lines[i] = line
                    p.write_text('\n'.join(lines) + '\n', encoding='utf-8')
                    return True, line
        if '## Profile' in lines:
            i = lines.index('## Profile') + 1
            while i < len(lines) and lines[i].startswith('- '):
                i += 1
            lines.insert(i, line)
        else:
            lines += ['', '## Profile', line]
        p.write_text('\n'.join(lines) + '\n', encoding='utf-8')
        return True, line
    for line in text.splitlines():
        if line.split(': ', 1)[-1].strip().lower() == clean.lower():
            return False, line
    line = f'- {today or _dt.date.today().isoformat()}: {clean}'
    with open(p, 'a', encoding='utf-8') as fh:
        if text and not text.endswith('\n'):
            fh.write('\n')
        fh.write(line + '\n')
    return True, line
