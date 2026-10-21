"""Temmo server mode: the project key (if any) stays on the server; users never enter a key. MIT.

Engine choice (docs/temmo/PROVIDERS.md):
- a cloud provider only if it has a real free API tier (FREE_TIER) AND an adult operator accepted its
  Terms (TEMMO_OPERATOR_TERMS_OK=1; the Gemini API Terms are 18+);
- otherwise local Gemma 4 on this machine; otherwise the deterministic mock.
Paid providers (Claude, OpenAI, DeepSeek, Nano Banana) are never used with a server key. A user may
still bring their own key (BYOK) as an advanced option; BYOK jobs skip the free quota.
Every user has a per-day quota and all jobs run through one FIFO queue (one generation at a time).
"""
from __future__ import annotations

import datetime
import json
import os
import re
import threading
import time
import uuid
from pathlib import Path

from .providers import ENV_KEYS, make

FREE_TIER = {"gemini"}
PAID_ONLY = {"anthropic", "openai", "deepseek", "gemini-image"}
USER_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
DEFAULT_LIMITS = {"build": 3, "remix": 20}


class TemmoError(Exception):
    def __init__(self, code: str, msg: str, status: int = 400, **extra):
        super().__init__(msg)
        self.code, self.status, self.extra = code, status, extra

    def as_dict(self):
        return dict({"error": self.code, "message": str(self)}, **self.extra)


def local_available() -> bool:
    try:
        from terai_router.sankpup.gemma import llama_cpp_available
        return bool(llama_cpp_available() or os.environ.get("TEMMO_GEMMA_PYTHON"))
    except Exception:
        return False


def pick_engine(env=None, local_ok=None) -> tuple[str, list]:
    env = os.environ if env is None else env
    notes: list = []
    want = env.get("TEMMO_FREE_TIER", "").strip().lower()
    if want:
        if want not in FREE_TIER:
            notes.append(f"{want}: no free API tier, refused for server mode")
        elif not env.get(ENV_KEYS[want], ""):
            notes.append(f"{want}: ${ENV_KEYS[want]} not set")
        elif env.get("TEMMO_OPERATOR_TERMS_OK", "") != "1":
            notes.append(f"{want}: Terms need an 18+ operator (set TEMMO_OPERATOR_TERMS_OK=1)")
        else:
            return want, notes
    if local_ok is None:
        local_ok = local_available()
    if local_ok:
        return "local", notes
    return "mock", notes + ["local Gemma not available, using mock"]


class Quota:
    """Per-user, per-day counters (UTC day). Also caps one IP at 5x a user's limit."""

    def __init__(self, path=None, limits=None, clock=time.time, env=None):
        env = os.environ if env is None else env
        self.limits = dict(limits or {k: int(env.get(f"TEMMO_QUOTA_{k.upper()}", v)) for k, v in DEFAULT_LIMITS.items()})
        self.path, self.clock, self.lock = (Path(path) if path else None), clock, threading.Lock()
        self.data = {}
        if self.path and self.path.exists():
            try:
                self.data = json.loads(self.path.read_text(encoding="utf-8"))
            except ValueError:
                self.data = {}

    def day(self) -> str:
        return datetime.datetime.fromtimestamp(self.clock(), datetime.timezone.utc).strftime("%Y-%m-%d")

    def resets_at(self) -> str:
        d = datetime.datetime.fromtimestamp(self.clock(), datetime.timezone.utc).date() + datetime.timedelta(days=1)
        return d.isoformat() + "T00:00:00Z"

    def _bucket(self):
        day = self.day()
        if self.data.get("day") != day:
            self.data = {"day": day, "users": {}, "ips": {}}
        return self.data

    def left(self, user: str, kind: str) -> int:
        with self.lock:
            used = self._bucket()["users"].get(user, {}).get(kind, 0)
        return max(0, self.limits[kind] - used)

    def take(self, user: str, kind: str, ip: str = "") -> bool:
        with self.lock:
            b = self._bucket()
            u = b["users"].setdefault(user, {})
            i = b["ips"].setdefault(ip, {}) if ip else {}
            if u.get(kind, 0) >= self.limits[kind] or (ip and i.get(kind, 0) >= 5 * self.limits[kind]):
                return False
            u[kind] = u.get(kind, 0) + 1
            if ip:
                i[kind] = i.get(kind, 0) + 1
            self._save()
            return True

    def refund(self, user: str, kind: str, ip: str = ""):
        with self.lock:
            b = self._bucket()
            for table, key in (("users", user), ("ips", ip)):
                c = b[table].get(key, {})
                if c.get(kind, 0) > 0:
                    c[kind] -= 1
            self._save()

    def _save(self):
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.data), encoding="utf-8")


class JobQueue:
    """One FIFO queue, one worker: the machine runs one generation at a time."""

    def __init__(self, work, max_pending: int = 20):
        self.work, self.max_pending = work, max_pending
        self.jobs: dict = {}
        self.pending: list = []
        self.cv = threading.Condition()
        self._thread = None

    def submit(self, user: str, kind: str, payload: dict) -> dict:
        with self.cv:
            if any(self.jobs[j]["user"] == user for j in self.pending):
                raise TemmoError("busy", "you already have a job in the queue", 429)
            if len(self.pending) >= self.max_pending:
                raise TemmoError("queue_full", "queue is full, try again later", 503)
            jid = uuid.uuid4().hex[:12]
            self.jobs[jid] = {"id": jid, "user": user, "kind": kind, "payload": payload, "state": "queued",
                              "created": time.time()}
            self.pending.append(jid)
            self.cv.notify()
            return self.status(jid)

    def status(self, jid: str) -> dict:
        j = self.jobs.get(jid)
        if not j:
            raise TemmoError("not_found", "no such job", 404)
        out = {k: v for k, v in j.items() if k not in ("payload", "user")}
        out["position"] = self.pending.index(jid) + 1 if jid in self.pending else 0
        return out

    def run_once(self) -> bool:
        with self.cv:
            if not self.pending:
                return False
            jid = self.pending.pop(0)
            job = self.jobs[jid]
            job["state"] = "running"
        t = time.time()
        try:
            job["result"] = self.work(job)
            job["state"] = "done"
        except Exception as e:
            job["state"], job["error"] = "failed", str(e)[:300]
        job["seconds"] = round(time.time() - t, 2)
        job["payload"] = {}  # drop inputs (BYOK keys) once the job ends
        return True

    def start(self):
        if self._thread is None:
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()

    def _loop(self):
        while True:
            with self.cv:
                while not self.pending:
                    self.cv.wait()
            self.run_once()


class TemmoServer:
    def __init__(self, root, env=None, quota=None, engine=None, builder=None, local_ok=None):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.env = os.environ if env is None else env
        if engine:
            self.engine, self.notes = engine, []
        else:
            self.engine, self.notes = pick_engine(self.env, local_ok)
        self.quota = quota or Quota(self.root / "quota.json", env=self.env)
        self.builder = builder
        self.queue = JobQueue(self._work)

    def info(self) -> dict:
        return {"engine": self.engine, "notes": self.notes, "limits": self.quota.limits, "free_tier": sorted(FREE_TIER),
                "byok": "optional", "queue": len(self.queue.pending), "resets_at": self.quota.resets_at()}

    def request(self, user: str, kind: str, payload: dict, ip: str = "", byok: dict | None = None) -> dict:
        if not USER_RE.match(str(user or "")):
            raise TemmoError("bad_user", "user id must be 1-64 letters, digits, _ or -")
        if kind not in self.quota.limits:
            raise TemmoError("bad_kind", f"kind must be one of {sorted(self.quota.limits)}")
        if kind == "build" and not (1 <= len(str(payload.get("idea", "")).strip()) <= 300):
            raise TemmoError("bad_idea", "idea must be 1-300 characters")
        if kind == "remix" and (not isinstance(payload.get("game"), dict) or not str(payload.get("instruction", "")).strip()):
            raise TemmoError("bad_remix", "remix needs game and instruction")
        if byok:
            if byok.get("provider") not in ENV_KEYS or not byok.get("key"):
                raise TemmoError("bad_byok", "byok needs provider and key")
            payload = dict(payload, _byok=byok)
        elif not self.quota.take(user, kind, ip):
            raise TemmoError("quota", f"daily {kind} quota used up", 429, left=0, resets_at=self.quota.resets_at())
        try:
            st = self.queue.submit(user, kind, dict(payload, _ip=ip))
        except TemmoError:
            if not byok:
                self.quota.refund(user, kind, ip)
            raise
        st["left"] = self.quota.left(user, kind)
        return st

    def _provider(self, payload):
        b = payload.get("_byok")
        if b:
            return make(b["provider"], env={ENV_KEYS[b["provider"]]: b["key"]}), b["provider"]
        return make(self.engine), self.engine

    def _work(self, job) -> dict:
        p = job["payload"]
        try:
            prov, name = self._provider(p)
            if job["kind"] == "remix":
                from .remix import remix
                game, patch, source = remix(p["game"], p["instruction"], prov)
                return {"game": game, "patch": patch, "source": source, "engine": name}
            out = self.root / "games" / job["id"]
            build = self.builder
            if build is None:
                from .pipeline import build
            roles = {r: name for r in ("design", "review", "code", "repair", "chat")}
            rep = build(p["idea"], out, roles=roles, seed=int(p.get("seed", 1)), screenshots=False)
            t = rep.get("test") or {}
            return {"html": rep["build"]["html"], "title": rep["gdd"]["title"], "passed": t.get("passed"), "engine": name}
        except Exception:
            if not p.get("_byok"):
                self.quota.refund(job["user"], job["kind"], p.get("_ip", ""))
            raise


def make_handler(srv: TemmoServer):
    from http.server import BaseHTTPRequestHandler
    from urllib.parse import parse_qs, urlparse

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):  # no request logs (they would hold user ids)
            pass

        def _send(self, code, obj=None, body=None, ctype="application/json"):
            data = body if body is not None else json.dumps(obj, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype + "; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", srv.env.get("TEMMO_CORS", "*"))
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()
            self.wfile.write(data)

        def do_OPTIONS(self):
            self._send(204, body=b"")

        def do_GET(self):
            u = urlparse(self.path)
            q = {k: v[0] for k, v in parse_qs(u.query).items()}
            try:
                if u.path == "/api/info":
                    return self._send(200, srv.info())
                if u.path == "/api/quota":
                    user = q.get("user", "")
                    return self._send(200, {k: srv.quota.left(user, k) for k in srv.quota.limits})
                if u.path == "/api/job":
                    return self._send(200, srv.queue.status(q.get("id", "")))
                m = re.match(r"^/games/([0-9a-f]{12})\.html$", u.path)
                if m:
                    st = srv.queue.status(m.group(1))
                    html = (st.get("result") or {}).get("html")
                    if html and Path(html).exists():
                        return self._send(200, body=Path(html).read_bytes(), ctype="text/html")
                return self._send(404, {"error": "not_found"})
            except TemmoError as e:
                return self._send(e.status, e.as_dict())

        def do_POST(self):
            try:
                n = int(self.headers.get("Content-Length") or 0)
                if n > 200_000:
                    raise TemmoError("too_big", "request too large", 413)
                body = json.loads(self.rfile.read(n) or b"{}")
                kind = {"/api/build": "build", "/api/remix": "remix"}.get(urlparse(self.path).path)
                if not kind:
                    raise TemmoError("not_found", "no such endpoint", 404)
                payload = {k: body.get(k) for k in ("idea", "seed", "game", "instruction") if k in body}
                st = srv.request(body.get("user"), kind, payload, ip=self.client_address[0], byok=body.get("byok"))
                return self._send(202, st)
            except TemmoError as e:
                return self._send(e.status, e.as_dict())
            except ValueError:
                return self._send(400, {"error": "bad_json"})

    return H


def serve(root="temmo-server", host="127.0.0.1", port=8765):
    from http.server import ThreadingHTTPServer
    srv = TemmoServer(root)
    srv.queue.start()
    httpd = ThreadingHTTPServer((host, port), make_handler(srv))
    print(f"Temmo server on http://{host}:{port} engine={srv.engine} limits={srv.quota.limits} {srv.notes}")
    httpd.serve_forever()
