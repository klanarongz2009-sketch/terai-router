"""Persistent local server for Tagentic relay mode: keeps the model loaded between relay commands.

    python -m terai_router.tagentic.server call -- <terai tagentic arguments>    what the relay wrapper runs
    python -m terai_router.tagentic.server serve [--home DIR]                   the server itself
    python -m terai_router.tagentic.server stop  [--home DIR]

``call`` sends the arguments to the server over a unix socket and prints what ``terai tagentic`` would have printed
(stdout, stderr and the exit code are passed through unchanged, so the relay JSON is the same). When no server is
running it starts one in the background and waits for its socket. When the server cannot start, or
TERAI_TAGENTIC_NO_SERVER=1, the command runs in this process as before (the model then loads every time).

The socket is a file in <memory folder>/run/ (folder mode 0700, socket 0600): nothing listens on a network port.
The server runs one request at a time, keeps one loaded model, and exits after TERAI_TAGENTIC_IDLE seconds without
a request (default 1800) to free the RAM. Because the model object stays loaded, llama.cpp reuses the KV cache of
the prompt prefix the turns share (the four memory files, the tool list, the earlier conversation): only the new
tokens of a turn are prefilled. A server started from older code exits when a client with newer code calls it.
"""
from __future__ import annotations

import contextlib
import fcntl
import io
import json
import os
import socket
import struct
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, Optional

from . import memory as M

SOCK_NAME = 'tagentic.sock'
LOCK_NAME = 'server.lock'
LOG_NAME = 'server.log'
PERF_NAME = 'perf.jsonl'
IDLE_DEFAULT = 1800.0
START_WAIT = 30.0   # seconds a client waits for a new server's socket


# ------------------------------------------------------------------------------------------------ helpers
def home_from_argv(argv: list) -> Path:
    """The memory folder the tagentic arguments point at (--memory-dir, else the default)."""
    for i, a in enumerate(argv):
        if a == '--memory-dir' and i + 1 < len(argv):
            return Path(argv[i + 1]).expanduser()
        if a.startswith('--memory-dir='):
            return Path(a.split('=', 1)[1]).expanduser()
    return Path(M.default_home())


def run_dir(home) -> Path:
    d = Path(home).expanduser() / 'run'
    d.mkdir(parents=True, exist_ok=True)
    os.chmod(d, 0o700)
    return d


def code_id() -> str:
    """Changes when the Tagentic or LocalLM source changes (newest mtime and total size of the files)."""
    here = Path(__file__).resolve().parent
    files = sorted(here.glob('*.py')) + [here.parent / 'brain' / 'local.py']
    st = [f.stat() for f in files if f.is_file()]
    return f'{max(s.st_mtime_ns for s in st)}-{sum(s.st_size for s in st)}'


def send_msg(sock: socket.socket, obj: dict) -> None:
    data = json.dumps(obj, ensure_ascii=False).encode('utf-8')
    sock.sendall(struct.pack('>I', len(data)) + data)


def recv_msg(sock: socket.socket) -> Optional[dict]:
    head = _recv_exact(sock, 4)
    if head is None:
        return None
    body = _recv_exact(sock, struct.unpack('>I', head)[0])
    return None if body is None else json.loads(body.decode('utf-8'))


def _recv_exact(sock: socket.socket, n: int) -> Optional[bytes]:
    buf = b''
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            return None
        buf += chunk
    return buf


# ------------------------------------------------------------------------------------------------ server
class Server:
    """One loaded model; runs ``terai tagentic`` argument lists one at a time."""

    def __init__(self, home, idle: Optional[float] = None, make_lm: Optional[Callable] = None,
                 run_cli: Optional[Callable] = None, clock: Callable[[], float] = time.monotonic) -> None:
        self.home = Path(home).expanduser()
        self.rd = run_dir(self.home)
        self.sock_path = self.rd / SOCK_NAME
        self.idle = float(os.environ.get('TERAI_TAGENTIC_IDLE') or IDLE_DEFAULT) if idle is None else idle
        self._make_lm = make_lm
        self._run_cli = run_cli
        self.clock = clock
        self.code = code_id()
        self.lm = None
        self.lm_key = None
        self.last = clock()
        self.requests = 0

    # one request ------------------------------------------------------------------------------------
    def handle(self, req: dict) -> dict:
        if req.get('op') == 'ping':
            return {'ok': True, 'pid': os.getpid(), 'code': self.code, 'loaded': self.lm is not None}
        if req.get('op') == 'stop':
            return {'ok': True, 'stopping': True}
        if req.get('code') and req['code'] != self.code:
            return {'restart': True, 'reason': 'server runs older code'}
        argv = [str(a) for a in req.get('argv') or []]
        from . import cli
        try:
            args = cli.build_parser().parse_args(argv)
        except SystemExit as e:   # argparse error: run it the normal way to get the same message and code
            return self._run(argv, None) if self._run_cli else {'rc': int(e.code or 2), 'stdout': '',
                                                                  'stderr': 'bad arguments'}
        key = cli.lm_key(args)
        if self.lm is None or key != self.lm_key:
            self.lm, self.lm_key = None, None
            self.lm = (self._make_lm or cli.make_lm)(args)   # loaded lazily inside the run: load_s stays honest
            self.lm_key = key
        n0 = len(getattr(self.lm, 'perf', []) or [])
        res = self._run(argv, self.lm)
        perf = (getattr(self.lm, 'perf', []) or [])[n0:]
        if perf:
            self._perf(argv, perf)
        return res

    def _run(self, argv: list, lm) -> dict:
        out, err = io.StringIO(), io.StringIO()
        run = self._run_cli
        if run is None:
            from .cli import main as run
        with contextlib.redirect_stderr(err):
            try:
                rc = run(argv, lm=lm, stdin=io.StringIO(''), stdout=out)
            except SystemExit as e:
                rc = int(e.code or 0) if isinstance(e.code, int) or e.code is None else 2
            except Exception as e:   # never take the server down with one bad turn
                print(f'tagentic server: {type(e).__name__}: {e}', file=sys.stderr)
                rc = 1
        return {'rc': int(rc or 0), 'stdout': out.getvalue(), 'stderr': err.getvalue()}

    def _perf(self, argv: list, perf: list) -> None:
        cmd = next((a for a in argv if a in ('--start', '--message', '--approve', '--deny', '--reset')), '')
        line = {'time': time.strftime('%Y-%m-%dT%H:%M:%S%z'), 'cmd': cmd.lstrip('-'), 'calls': perf,
                'load_s': getattr(self.lm, 'load_seconds', 0.0)}
        try:
            with open(self.rd / PERF_NAME, 'a', encoding='utf-8') as f:
                f.write(json.dumps(line, ensure_ascii=False) + '\n')
        except OSError:
            pass

    # the loop ---------------------------------------------------------------------------------------
    def serve(self, lock_wait: float = 3.0) -> int:
        lock = open(self.rd / LOCK_NAME, 'w')
        deadline = time.monotonic() + lock_wait   # an old server may still be shutting down
        while True:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    lock.close()
                    return 0   # another server owns this memory folder
                time.sleep(0.05)
        with contextlib.suppress(FileNotFoundError):
            self.sock_path.unlink()
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        old = os.umask(0o177)
        try:
            srv.bind(str(self.sock_path))
        finally:
            os.umask(old)
        os.chmod(self.sock_path, 0o600)
        srv.listen(8)
        srv.settimeout(min(30.0, max(0.05, self.idle / 4)))
        lock.write(str(os.getpid()))
        lock.flush()
        try:
            while True:
                if self.clock() - self.last > self.idle:
                    break
                try:
                    conn, _ = srv.accept()
                except socket.timeout:
                    continue
                stop = False
                with conn:
                    conn.settimeout(None)
                    try:
                        req = recv_msg(conn)
                        if req is None:
                            continue
                        res = self.handle(req)
                        self.requests += 1
                        send_msg(conn, res)
                        stop = bool(res.get('stopping') or res.get('restart'))
                    except (OSError, ValueError) as e:
                        print(f'tagentic server: {type(e).__name__}: {e}', file=sys.stderr)
                    finally:
                        self.last = self.clock()   # idle time counts from the end of the last request
                if stop:
                    break
        finally:
            srv.close()
            with contextlib.suppress(FileNotFoundError):
                self.sock_path.unlink()
            self.lm = None
            lock.close()
        return 0


# ------------------------------------------------------------------------------------------------ client
def _connect(path: Path) -> Optional[socket.socket]:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        s.connect(str(path))
        return s
    except OSError:
        s.close()
        return None


def spawn_server(home: Path) -> None:
    rd = run_dir(home)
    log = open(rd / LOG_NAME, 'a')
    env = dict(os.environ)
    subprocess.Popen([sys.executable, '-m', 'terai_router.tagentic.server', 'serve', '--home', str(home)],
                     stdin=subprocess.DEVNULL, stdout=log, stderr=log, env=env, start_new_session=True,
                     close_fds=True)
    log.close()


def ensure_server(home: Path, wait: float = START_WAIT, spawn: Callable = spawn_server,
                  sleep: Callable = time.sleep) -> Optional[socket.socket]:
    path = run_dir(home) / SOCK_NAME
    s = _connect(path)
    if s is not None:
        return s
    spawn(home)
    deadline = time.monotonic() + wait
    while time.monotonic() < deadline:
        sleep(0.1)
        s = _connect(path)
        if s is not None:
            return s
    return None


def local_run(argv: list) -> int:
    from .cli import main
    return main(argv)


def call(argv: list, out=None, err=None, ensure: Callable = ensure_server, fallback: Callable = local_run) -> int:
    """Run ``terai tagentic <argv>`` on the server (started when needed); fall back to this process."""
    out = out or sys.stdout
    err = err or sys.stderr
    if os.environ.get('TERAI_TAGENTIC_NO_SERVER') == '1':
        return fallback(argv)
    home = home_from_argv(argv)
    code = code_id()
    for _attempt in range(2):   # a second try only when an old server asked to be restarted
        s = ensure(home)
        if s is None:
            print('tagentic: server did not start; running without it (the model loads in this process)', file=err)
            return fallback(argv)
        with s:
            try:
                send_msg(s, {'op': 'run', 'argv': argv, 'code': code})
                res = recv_msg(s)
            except OSError as e:
                res, why = None, f'{type(e).__name__}: {e}'
            else:
                why = 'connection closed'
        if res is None:   # the server died during the turn: report it, do not run the turn twice
            print(f'tagentic: server failed during the command ({why}); see {run_dir(home) / LOG_NAME}', file=err)
            return 1
        if res.get('restart'):
            _wait_gone(run_dir(home) / SOCK_NAME)
            continue
        if res.get('stdout'):
            out.write(res['stdout'])
            out.flush()
        if res.get('stderr'):
            err.write(res['stderr'])
            err.flush()
        return int(res.get('rc') or 0)
    print('tagentic: server kept asking for a restart; running without it', file=err)
    return fallback(argv)


def _wait_gone(path: Path, wait: float = 10.0) -> None:
    deadline = time.monotonic() + wait
    while path.exists() and time.monotonic() < deadline:
        time.sleep(0.1)


def stop(home: Path) -> bool:
    s = _connect(run_dir(home) / SOCK_NAME)
    if s is None:
        return False
    with s:
        send_msg(s, {'op': 'stop'})
        recv_msg(s)
    return True


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print(__doc__, file=sys.stderr)
        return 2
    cmd, rest = argv[0], argv[1:]
    if cmd == 'call':
        if rest[:1] == ['--']:
            rest = rest[1:]
        return call(rest)
    home = Path(M.default_home())
    if rest[:1] == ['--home'] and len(rest) > 1:
        home = Path(rest[1]).expanduser()
    if cmd == 'serve':
        return Server(home).serve()
    if cmd == 'stop':
        print('stopped' if stop(home) else 'no server running')
        return 0
    print(f'unknown command: {cmd} (call|serve|stop)', file=sys.stderr)
    return 2


if __name__ == '__main__':
    raise SystemExit(main())
