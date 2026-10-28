"""Tagentic persistent relay server: lifecycle, client fallback, early JSON stop, thread tuning (no model needed)."""
import io
import json
import os
import stat
import threading
import time

import pytest

from terai_router.brain import local as L
from terai_router.tagentic import cli as C
from terai_router.tagentic import server as S


class DummyLM:
    def __init__(self, args=None):
        self.args = args
        self.perf = []
        self.load_seconds = 0.0


def fake_cli(argv, lm=None, stdin=None, stdout=None):
    """Stands in for cli.main: echoes argv and which model object it got."""
    import sys
    if lm is not None:
        lm.perf.append({'seconds': 0.01, 'prefill_tokens': 1, 'gen_tokens': 1})
    stdout.write(json.dumps({'argv': argv, 'lm': id(lm)}) + '\n')
    print('trace line', file=sys.stderr)
    return 3 if '--approve' in argv else 0


BASE = ['-w', 'ws', '--session', 's1', '--json']


# ---------------------------------------------------------------------------------------------- handle()
def test_model_object_is_reused_between_requests(tmp_path):
    made = []
    srv = S.Server(tmp_path, idle=60, make_lm=lambda a: made.append(DummyLM(a)) or made[-1], run_cli=fake_cli)
    r1 = srv.handle({'op': 'run', 'argv': BASE + ['--start'], 'code': srv.code})
    r2 = srv.handle({'op': 'run', 'argv': BASE + ['--message', 'hi'], 'code': srv.code})
    assert len(made) == 1
    assert json.loads(r1['stdout'])['lm'] == json.loads(r2['stdout'])['lm'] == id(made[0])
    assert r1['rc'] == 0 and 'trace line' in r1['stderr']
    perf = (tmp_path / 'run' / S.PERF_NAME).read_text().splitlines()
    assert [json.loads(p)['cmd'] for p in perf] == ['start', 'message']


def test_new_model_when_model_settings_change(tmp_path):
    made = []
    srv = S.Server(tmp_path, idle=60, make_lm=lambda a: made.append(DummyLM(a)) or made[-1], run_cli=fake_cli)
    srv.handle({'op': 'run', 'argv': BASE + ['--start']})
    srv.handle({'op': 'run', 'argv': BASE + ['--ctx', '4096', '--start']})
    assert len(made) == 2


def test_exit_code_passes_through(tmp_path):
    srv = S.Server(tmp_path, idle=60, make_lm=DummyLM, run_cli=fake_cli)
    assert srv.handle({'op': 'run', 'argv': BASE + ['--approve']})['rc'] == 3


def test_old_code_asks_for_restart(tmp_path):
    srv = S.Server(tmp_path, idle=60, make_lm=DummyLM, run_cli=fake_cli)
    assert srv.handle({'op': 'run', 'argv': BASE + ['--start'], 'code': 'newer'}) == {
        'restart': True, 'reason': 'server runs older code'}


def test_crash_in_turn_does_not_kill_server(tmp_path):
    def boom(argv, lm=None, stdin=None, stdout=None):
        raise RuntimeError('bad turn')
    srv = S.Server(tmp_path, idle=60, make_lm=DummyLM, run_cli=boom)
    r = srv.handle({'op': 'run', 'argv': BASE + ['--start']})
    assert r['rc'] == 1 and 'bad turn' in r['stderr']


def test_home_from_argv(monkeypatch, tmp_path):
    assert S.home_from_argv(['--memory-dir', str(tmp_path)]) == tmp_path
    assert S.home_from_argv([f'--memory-dir={tmp_path}']) == tmp_path
    monkeypatch.setenv('TERAI_TAGENTIC_HOME', str(tmp_path / 'h'))
    assert S.home_from_argv(BASE) == tmp_path / 'h'


# ---------------------------------------------------------------------------------------------- serve() + call()
def start_server(home, idle=30.0, run_cli=fake_cli):
    srv = S.Server(home, idle=idle, make_lm=DummyLM, run_cli=run_cli)
    t = threading.Thread(target=srv.serve, daemon=True)
    t.start()
    sock = home / 'run' / S.SOCK_NAME
    for _ in range(500):
        if sock.exists():
            break
        time.sleep(0.01)
    return srv, t, sock


def no_spawn(home):
    raise AssertionError('should not spawn')


def test_call_goes_through_running_server(tmp_path):
    srv, t, sock = start_server(tmp_path)
    assert stat.S_IMODE(os.stat(sock).st_mode) == 0o600
    assert stat.S_IMODE(os.stat(tmp_path / 'run').st_mode) == 0o700
    out, err = io.StringIO(), io.StringIO()
    argv = ['--memory-dir', str(tmp_path)] + BASE + ['--start']
    rc = S.call(argv, out=out, err=err, ensure=lambda h: S.ensure_server(h, spawn=no_spawn),
                fallback=lambda a: pytest.fail('fallback used'))
    assert rc == 0
    assert json.loads(out.getvalue())['argv'] == argv   # stdout unchanged: the relay JSON is the same
    assert err.getvalue() == 'trace line\n'
    rc = S.call(argv[:-1] + ['--approve'], out=io.StringIO(), err=io.StringIO(),
                ensure=lambda h: S.ensure_server(h, spawn=no_spawn), fallback=lambda a: 99)
    assert rc == 3
    assert S.stop(tmp_path)
    t.join(5)
    assert not t.is_alive() and not sock.exists()


def test_server_exits_after_idle(tmp_path):
    srv, t, sock = start_server(tmp_path, idle=0.3)
    t.join(5)
    assert not t.is_alive()
    assert not sock.exists()


def test_second_server_on_same_folder_exits(tmp_path):
    srv, t, sock = start_server(tmp_path)
    assert S.Server(tmp_path, idle=30, make_lm=DummyLM, run_cli=fake_cli).serve(lock_wait=0) == 0   # lock held: returns
    assert sock.exists()
    S.stop(tmp_path)
    t.join(5)


def test_ensure_spawns_when_no_server(tmp_path):
    spawned = []

    def spawn(home):
        spawned.append(home)
        start_server(home)
    s = S.ensure_server(tmp_path, wait=5, spawn=spawn)
    assert s is not None and spawned == [tmp_path]
    s.close()
    S.stop(tmp_path)


def test_fallback_when_server_cannot_start(tmp_path):
    used = []
    err = io.StringIO()
    rc = S.call(['--memory-dir', str(tmp_path), '--start'], out=io.StringIO(), err=err,
                ensure=lambda h: S.ensure_server(h, wait=0.3, spawn=lambda home: None),
                fallback=lambda a: used.append(a) or 0)
    assert rc == 0 and used and 'running without it' in err.getvalue()


def test_no_server_env_runs_in_process(tmp_path, monkeypatch):
    monkeypatch.setenv('TERAI_TAGENTIC_NO_SERVER', '1')
    rc = S.call(['--start'], ensure=lambda h: pytest.fail('server used'), fallback=lambda a: 7)
    assert rc == 7


def test_server_death_mid_turn_is_reported_not_rerun(tmp_path):
    srv, t, sock = start_server(tmp_path, run_cli=None)
    srv._run = lambda argv, lm: (_ for _ in ()).throw(OSError('gone'))
    srv._make_lm = DummyLM
    err = io.StringIO()
    rc = S.call(['--memory-dir', str(tmp_path)] + BASE + ['--start'], out=io.StringIO(), err=err,
                ensure=lambda h: S.ensure_server(h, spawn=no_spawn), fallback=lambda a: pytest.fail('rerun'))
    assert rc == 1 and 'server failed during the command' in err.getvalue()
    S.stop(tmp_path)
    t.join(5)


def test_restart_request_retries_on_fresh_server(tmp_path):
    calls = []

    def ensure(home):
        srv, t, sock = start_server(home)
        if not calls:
            srv.code = 'old'   # first server runs older code
        calls.append(srv)
        return S._connect(sock)
    out = io.StringIO()
    rc = S.call(['--memory-dir', str(tmp_path)] + BASE + ['--start'], out=out, err=io.StringIO(), ensure=ensure,
                fallback=lambda a: pytest.fail('fallback'))
    assert rc == 0 and len(calls) == 2 and json.loads(out.getvalue())['argv'][-2:] == ['--json', '--start']
    S.stop(tmp_path)


# ---------------------------------------------------------------------------------------------- LocalLM bits
def test_json_complete():
    assert not L.json_complete('{"a": "}"')
    assert L.json_complete('{"a": "}"}')
    assert L.json_complete('{"a": {"b": 1}} trailing')
    assert not L.json_complete('{"a": "\\"}"')
    assert not L.json_complete('no json')


def test_stream_stops_at_closing_brace():
    pulled = []

    def gen():
        for piece in ['{"think": "x', '", "tool": "final"', '}', '\n\n', '   ']:
            pulled.append(piece)
            yield {'choices': [{'delta': {'content': piece}}]}
    it = gen()
    text, n, early = L._stream_until_json(it)
    assert text == '{"think": "x", "tool": "final"}' and early and n == 3
    assert pulled[-1] == '}' and it.gi_frame is None   # generator closed


def test_tuned_threads_leave_cores_free():
    assert C.tuned_threads(8) == (6, 7)
    assert C.tuned_threads(4) == (2, 3)
    assert C.tuned_threads(2) == (2, 2)


def test_make_lm_uses_tuned_settings(monkeypatch):
    monkeypatch.delenv('TERAI_TAGENTIC_THREADS', raising=False)
    monkeypatch.delenv('TERAI_TAGENTIC_THREADS_BATCH', raising=False)
    monkeypatch.setattr(os, 'cpu_count', lambda: 8)
    lm = C.make_lm(C.build_parser().parse_args(['--start']))
    assert (lm.threads, lm.threads_batch, lm.flash_attn, lm.n_ctx) == (6, 7, True, 8192)
    lm = C.make_lm(C.build_parser().parse_args(['--threads', '3', '--start']))
    assert (lm.threads, lm.threads_batch) == (3, 3)
