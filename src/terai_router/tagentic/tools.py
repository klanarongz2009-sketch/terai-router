"""Tagentic1 tools. File tools stay inside the workspace; writes, code and shell runs need the user's confirmation.

Each call returns a ToolResult: ``output`` goes back to the model, ``note`` is the short line shown in the trace
(written here by code from what really happened, never by the model).

No network tool in v1. ``run_shell`` and ``run_python`` start in the workspace folder but are not a jail: that is
why they always ask first (or need ``--yes``).
"""
from __future__ import annotations

import fnmatch
import mimetypes
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from . import memory as M
from .workspace import SandboxError, Workspace

SKIP_DIRS = {'.git', '__pycache__', 'node_modules', '.venv', 'venv', '.mypy_cache', '.pytest_cache', '.tox'}
READ_MAX_BYTES = 2_000_000     # larger text files are read as a window from the start only
OUTPUT_MAX = 6000              # characters of tool output sent back to the model
MAGIC = [
    (b'\x89PNG\r\n\x1a\n', 'PNG image'), (b'\xff\xd8\xff', 'JPEG image'), (b'GIF8', 'GIF image'),
    (b'%PDF', 'PDF document'), (b'PK\x03\x04', 'ZIP archive (or docx/xlsx/jar/wheel)'), (b'GGUF', 'GGUF model weights'),
    (b'\x7fELF', 'ELF executable'), (b'ID3', 'MP3 audio'), (b'OggS', 'Ogg audio'), (b'fLaC', 'FLAC audio'),
    (b'\x1f\x8b', 'gzip archive'), (b'SQLite format 3', 'SQLite database'), (b'\x00asm', 'WebAssembly'),
]


class PendingAction(Exception):
    """Raised by a relay-mode confirm callback: the gated call waits for --approve / --deny in a later command."""

    def __init__(self, tool: str, args: dict, summary: str) -> None:
        super().__init__(f'{tool} waits for approval')
        self.tool, self.call_args, self.summary = tool, dict(args or {}), summary


@dataclass
class ToolResult:
    ok: bool
    output: str
    note: str


def human_size(n: int) -> str:
    for unit in ('bytes', 'KB', 'MB', 'GB'):
        if n < 1024 or unit == 'GB':
            return f'{n} {unit}' if unit == 'bytes' else f'{n:.1f} {unit}'
        n /= 1024
    return f'{n} bytes'


def sniff(path: Path) -> tuple:
    """(is_text, kind). Text = no NUL byte in the first 8 KB and valid UTF-8 there."""
    with open(path, 'rb') as fh:
        head = fh.read(8192)
    for sig, kind in MAGIC:
        if head.startswith(sig):
            return False, kind
    if head[:4] == b'RIFF' and head[8:12] in (b'WAVE', b'WEBP', b'AVI '):
        return False, {b'WAVE': 'WAV audio', b'WEBP': 'WebP image', b'AVI ': 'AVI video'}[head[8:12]]
    if b'\x00' in head:
        return False, mimetypes.guess_type(str(path))[0] or 'binary data'
    try:
        head.decode('utf-8')
    except UnicodeDecodeError as e:
        if e.start < len(head) - 4:   # a multi-byte character cut at the 8 KB edge is fine
            return False, mimetypes.guess_type(str(path))[0] or 'binary data (not UTF-8 text)'
    return True, mimetypes.guess_type(str(path))[0] or 'text'


def _clip(text: str, limit: int = OUTPUT_MAX) -> str:
    return text if len(text) <= limit else text[:limit] + f'\n... (cut, {len(text) - limit} more characters)'


def _int(v, default: int, lo: int = 1, hi: int = 100000) -> int:
    try:
        return max(lo, min(hi, int(v)))
    except (TypeError, ValueError):
        return default


TOOL_SPECS = {
    # name: (gated, args, description)
    'list_files':   (False, 'path=".", pattern="*", max=200', 'list files and folders under a path (skips .git, venvs, caches)'),
    'read_file':    (False, 'path, start=1, lines=200', 'read a text file with line numbers; a binary file is reported by type and size'),
    'search_files': (False, 'query, path=".", regex=false, max=50', 'search text in files (case-insensitive)'),
    'write_file':   (True, 'path, content', 'create or overwrite a text file (asks the user)'),
    'edit_file':    (True, 'path, old, new, replace_all=false', 'replace text that appears exactly once, or every time with replace_all (asks the user)'),
    'run_python':   (True, 'code', 'run Python code in the workspace folder (asks the user)'),
    'run_shell':    (True, 'command', 'run a shell command in the workspace folder (asks the user)'),
    'calculator':   (False, 'expression', 'arithmetic, from TERAI1'),
    'datetime':     (False, 'query', 'current date and time or date arithmetic, from TERAI1'),
    'units':        (False, 'query', 'unit conversion, from TERAI1'),
    'remember':     (True, 'fact, file="Memory.md"', 'save one durable fact: file="Memory.md" (permanent memory) or file="User.md" (who the user is, e.g. "ชื่อ: ..."); never secrets or transcripts (asks the user)'),
}


class Toolbox:
    def __init__(self, workspace: Workspace | str | None = None, home: str | os.PathLike | None = None,
                 confirm: Optional[Callable[[str, str], bool]] = None, yes: bool = False,
                 tool_timeout: float = 60.0, now=None) -> None:
        self.ws = workspace if isinstance(workspace, Workspace) else Workspace(workspace)
        self.home = home
        self.confirm = confirm
        self.yes = yes
        self.tool_timeout = tool_timeout
        self.now = now
        self.relay = False   # relay mode: a gated call raises PendingAction (resumed later with allow=True/False)
        self._chat = None

    @property
    def names(self) -> list:
        return list(TOOL_SPECS)

    def describe(self) -> str:
        return '\n'.join(f'- {n}({a}): {d}' for n, (_, a, d) in TOOL_SPECS.items())

    # ------------------------------------------------------------------------------------------- dispatch
    def call(self, name: str, args: dict | None, allow: Optional[bool] = None) -> ToolResult:
        """``allow`` is the user's decision on a resumed pending call (relay mode): True runs it, False denies it."""
        args = args if isinstance(args, dict) else {}
        if name not in TOOL_SPECS:
            return ToolResult(False, f'unknown tool: {name}. Tools: {", ".join(TOOL_SPECS)}', f'ไม่มี tool "{name}"')
        gated = TOOL_SPECS[name][0]
        if gated and not (allow if allow is not None else self._allowed(name, args)):
            return ToolResult(False, f'the user did not allow {name}. Do not retry the same call; '
                                     'explain what you wanted to do in the final answer.', 'ผู้ใช้ไม่อนุญาต')
        try:
            return getattr(self, '_t_' + name)(**args)
        except SandboxError as e:
            return ToolResult(False, str(e), 'ถูกบล็อก: path อยู่นอก workspace')
        except TypeError as e:
            return ToolResult(False, f'bad arguments for {name}: {e}. Expected: {TOOL_SPECS[name][1]}', 'อาร์กิวเมนต์ผิด')
        except FileNotFoundError as e:
            return ToolResult(False, f'not found: {e.filename or e}', 'ไม่พบไฟล์')
        except IsADirectoryError as e:
            return ToolResult(False, f'is a folder, not a file: {e.filename or e}', 'เป็นโฟลเดอร์ ไม่ใช่ไฟล์')
        except M.MemoryRejected as e:
            return ToolResult(False, f'not stored: {e}', 'ไม่บันทึก: ' + str(e)[:60])
        except OSError as e:
            return ToolResult(False, f'{type(e).__name__}: {e}', f'error: {type(e).__name__}')

    def summary(self, name: str, args: dict) -> str:
        if name == 'write_file':
            return f'เขียนไฟล์ {args.get("path")} ({len(str(args.get("content", "")).encode("utf-8"))} bytes)'
        if name == 'edit_file':
            return f'แก้ไฟล์ {args.get("path")}'
        if name == 'run_python':
            return 'run Python:\n' + str(args.get('code', ''))
        if name == 'run_shell':
            return f'run shell: {args.get("command", "")}'
        if name == 'remember':
            return f'บันทึกลง {args.get("file") or "Memory.md"}: {args.get("fact", "")}'
        return name

    def _allowed(self, name: str, args: dict) -> bool:
        if self.yes:
            return True
        if self.relay:
            raise PendingAction(name, args, self.summary(name, args))
        if self.confirm is None:
            return False
        try:
            return bool(self.confirm(name, self.summary(name, args)))
        except (EOFError, KeyboardInterrupt):
            return False

    # ------------------------------------------------------------------------------------------- file tools
    def _walk(self, base: Path):
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
            yield Path(dirpath), dirnames, sorted(filenames)

    def _t_list_files(self, path: str = '.', pattern: str = '*', max: int = 200) -> ToolResult:  # noqa: A002
        base = self.ws.resolve(path)
        if base.is_file():
            return ToolResult(True, f'{self.ws.rel(base)} ({human_size(base.stat().st_size)})', 'เป็นไฟล์ 1 ไฟล์')
        if not base.is_dir():
            raise FileNotFoundError(2, 'not found', str(path))
        limit = _int(max, 200, 1, 2000)
        lines, nfiles, ndirs, more = [], 0, 0, False
        for d, dirnames, filenames in self._walk(base):
            for sub in dirnames:
                ndirs += 1
                if pattern in ('*', '') and len(lines) < limit:
                    lines.append(self.ws.rel(d / sub) + '/')
            for f in filenames:
                if not fnmatch.fnmatch(f, pattern or '*'):
                    continue
                nfiles += 1
                if len(lines) < limit:
                    p = d / f
                    try:
                        size = human_size(p.stat().st_size)
                    except OSError:
                        size = '?'
                    lines.append(f'{self.ws.rel(p)} ({size})')
                else:
                    more = True
        if more or len(lines) >= limit:
            lines.append(f'... (showing {limit}; use path or pattern to narrow)')
        return ToolResult(True, '\n'.join(lines) or '(empty)', f'พบ {nfiles} ไฟล์ {ndirs} โฟลเดอร์')

    def _t_read_file(self, path: str, start: int = 1, lines: int = 200) -> ToolResult:
        p = self.ws.resolve(path)
        if p.is_dir():
            raise IsADirectoryError(21, 'is a folder', str(path))
        size = p.stat().st_size
        is_text, kind = sniff(p)
        rel = self.ws.rel(p)
        if not is_text:
            return ToolResult(True, f'{rel}: binary file, {kind}, {human_size(size)} ({size} bytes). '
                                    'Content not shown.', f'ไฟล์ binary: {kind}, {human_size(size)}')
        with open(p, 'rb') as fh:
            raw = fh.read(READ_MAX_BYTES)
        text = raw.decode('utf-8', errors='replace')
        all_lines = text.splitlines()
        total = len(all_lines)
        s = _int(start, 1, 1, max(1, total))
        n = _int(lines, 200, 1, 1000)
        window = all_lines[s - 1:s - 1 + n]
        width = len(str(s + len(window)))
        body = '\n'.join(f'{i:>{width}}| {line}' for i, line in enumerate(window, s))
        cut = ' (file larger than 2 MB: only the start was read)' if size > READ_MAX_BYTES else ''
        head = f'{rel} ({total} lines, {human_size(size)}){cut}\n'
        end = s + len(window) - 1
        note = f'อ่านบรรทัด {s}-{end} จาก {total}' if total else 'ไฟล์ว่าง'
        return ToolResult(True, _clip(head + body), note)

    def _t_search_files(self, query: str, path: str = '.', regex: bool = False, max: int = 50) -> ToolResult:  # noqa: A002
        if not str(query or '').strip():
            return ToolResult(False, 'query is empty', 'query ว่าง')
        base = self.ws.resolve(path)
        try:
            rx = re.compile(query if regex else re.escape(query), re.I)
        except re.error as e:
            return ToolResult(False, f'bad regex: {e}', 'regex ผิด')
        limit = _int(max, 50, 1, 500)
        files = [base] if base.is_file() else [d / f for d, _, fs in self._walk(base) for f in fs]
        hits, nfiles = [], set()
        for p in files:
            try:
                if p.stat().st_size > READ_MAX_BYTES or not sniff(p)[0]:
                    continue
                text = p.read_text(encoding='utf-8', errors='replace')
            except OSError:
                continue
            for i, line in enumerate(text.splitlines(), 1):
                if rx.search(line):
                    nfiles.add(p)
                    if len(hits) < limit:
                        hits.append(f'{self.ws.rel(p)}:{i}: {line.strip()[:200]}')
        total = sum(1 for _ in hits)
        out = '\n'.join(hits) or 'no match'
        if len(hits) >= limit:
            out += f'\n... (first {limit} matches)'
        return ToolResult(True, _clip(out), f'พบ {total} จุดใน {len(nfiles)} ไฟล์' if hits else 'ไม่พบ')

    def _t_write_file(self, path: str, content: str) -> ToolResult:
        p = self.ws.resolve(path)
        if p.is_dir():
            raise IsADirectoryError(21, 'is a folder', str(path))
        existed = p.exists()
        p.parent.mkdir(parents=True, exist_ok=True)
        data = str(content)
        p.write_text(data, encoding='utf-8')
        n = len(data.encode('utf-8'))
        verb = 'เขียนทับ' if existed else 'สร้าง'
        return ToolResult(True, f'wrote {self.ws.rel(p)} ({n} bytes, {len(data.splitlines())} lines)',
                          f'{verb} {self.ws.rel(p)} {n} bytes')

    def _t_edit_file(self, path: str, old: str, new: str, replace_all: bool = False) -> ToolResult:
        p = self.ws.resolve(path)
        is_text, kind = sniff(p)
        if not is_text:
            return ToolResult(False, f'{self.ws.rel(p)} is a binary file ({kind}); not edited', 'ไม่แก้: เป็นไฟล์ binary')
        text = p.read_text(encoding='utf-8')
        if not old:
            return ToolResult(False, 'old is empty', 'old ว่าง')
        count = text.count(old)
        if count == 0:
            return ToolResult(False, 'old text not found; read the file again and copy it exactly', 'ไม่พบข้อความเดิม')
        if count > 1 and not replace_all:
            return ToolResult(False, f'old text appears {count} times; give more context or set replace_all',
                              f'ข้อความเดิมซ้ำ {count} ที่')
        text = text.replace(old, new) if replace_all else text.replace(old, new, 1)
        p.write_text(text, encoding='utf-8')
        n = count if replace_all else 1
        return ToolResult(True, f'edited {self.ws.rel(p)}: {n} replacement(s)', f'แก้ {self.ws.rel(p)} {n} จุด')

    # ------------------------------------------------------------------------------------------- run tools
    def _run(self, argv, shell: bool) -> ToolResult:
        try:
            cp = subprocess.run(argv, shell=shell, cwd=str(self.ws.root), capture_output=True, text=True,
                                timeout=self.tool_timeout, stdin=subprocess.DEVNULL)
        except subprocess.TimeoutExpired:
            return ToolResult(False, f'timed out after {self.tool_timeout:g} s', f'เกินเวลา {self.tool_timeout:g} วินาที')
        out = (cp.stdout or '') + (('\n[stderr]\n' + cp.stderr) if cp.stderr else '')
        last = next((x.strip() for x in reversed(out.strip().splitlines()) if x.strip()), '')
        note = f'exit {cp.returncode}' + (f': {last[:70]}' if last else '')
        return ToolResult(cp.returncode == 0, _clip(f'exit code {cp.returncode}\n{out}'.rstrip()), note)

    def _t_run_python(self, code: str) -> ToolResult:
        # not -I: the workspace folder must stay importable for checks
        return self._run([sys.executable, '-E', '-s', '-c', str(code)], shell=False)

    def _t_run_shell(self, command: str) -> ToolResult:
        return self._run(str(command), shell=True)

    # ------------------------------------------------------------------------------------------- TERAI1 tools
    def _chat_tool(self, method: str, arg: str) -> ToolResult:
        from ..chat import Chat, normalize
        if self._chat is None:
            self._chat = Chat(now=self.now)
        a = str(arg or '').strip()
        got = getattr(self._chat, method)(a, normalize(a))
        if not got:
            return ToolResult(False, f'{method.strip("_")} could not read: {a}', 'อ่าน input ไม่ออก')
        return ToolResult(True, got, got if len(got) <= 80 else got[:79] + '…')

    def _t_calculator(self, expression: str) -> ToolResult:
        return self._chat_tool('_calc', expression)

    def _t_datetime(self, query: str = 'วันนี้วันที่เท่าไหร่') -> ToolResult:
        return self._chat_tool('_datetime', query)

    def _t_units(self, query: str) -> ToolResult:
        return self._chat_tool('_units', query)

    # ------------------------------------------------------------------------------------------- memory
    def _t_remember(self, fact: str, file: str = 'Memory.md') -> ToolResult:
        target = 'User.md' if str(file or '').strip().lower() in ('user.md', 'user') else (
            'Memory.md' if str(file or '').strip().lower() in ('memory.md', 'memory', '') else str(file))
        added, line = M.append_fact(self.home, fact, target=target)
        if not added:
            return ToolResult(True, f'already in {target}: {line}', f'มีอยู่แล้วใน {target}')
        return ToolResult(True, f'saved in {target}: {line}', f'บันทึก 1 บรรทัดใน {target}')
