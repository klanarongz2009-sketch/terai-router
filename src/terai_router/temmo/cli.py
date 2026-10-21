"""`terai temmo`: build a complete small game from an idea."""
from __future__ import annotations

import argparse
import json
import sys

from .providers import DEFAULT_MODELS, DEFAULT_ROLES, ENV_KEYS, resolve_roles


def build_parser(prog="terai temmo") -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog=prog, description="Temmo 1.0: AI that builds a complete small indie game (BYOK).")
    p.add_argument("idea", nargs="*", help="game idea (Thai or English)")
    p.add_argument("-o", "--out", default="temmo-out", help="output folder")
    p.add_argument("--seed", type=int, default=1)
    for role in DEFAULT_ROLES:
        p.add_argument(f"--{role}", dest=f"role_{role}", help=f"provider for {role} (default {DEFAULT_ROLES[role]})")
    p.add_argument("--all", dest="all_provider", help="one provider for every text role (e.g. local, mock, anthropic)")
    p.add_argument("--no-test", action="store_true")
    p.add_argument("--no-voice", action="store_true")
    p.add_argument("--no-mod", action="store_true")
    p.add_argument("--providers", action="store_true", help="show which provider each role will use, then exit")
    p.add_argument("--replay", action="store_true", help="reuse model replies saved in OUT/replies (no new model calls)")
    p.add_argument("--json", action="store_true")
    return p


def main(argv=None) -> int:
    import sys
    args = list(sys.argv[1:] if argv is None else argv)
    if args[:1] == ["serve"]:  # terai temmo serve [--root DIR] [--host H] [--port N]
        import argparse
        from .server import serve
        sp = argparse.ArgumentParser(prog="terai temmo serve", description="Temmo server mode: key on the server, "
                                     "per-user daily quota, one queue. Engine: free tier (if allowed) > local Gemma > mock.")
        sp.add_argument("--root", default="temmo-server")
        sp.add_argument("--host", default="127.0.0.1")
        sp.add_argument("--port", type=int, default=8765)
        s = sp.parse_args(args[1:])
        serve(s.root, s.host, s.port)
        return 0
    a = build_parser().parse_args(args)
    over = {r: getattr(a, f"role_{r}") for r in DEFAULT_ROLES if getattr(a, f"role_{r}")}
    if a.all_provider:
        over = dict({r: a.all_provider for r in DEFAULT_ROLES if r != "image"}, **over)
    roles = resolve_roles(over)
    if a.providers:
        for r, n in roles.items():
            want = over.get(r, DEFAULT_ROLES[r])
            note = "" if n == want else f"  (wanted {want}: no ${ENV_KEYS.get(want, '?')})"
            print(f"{r:7s} -> {n:12s} {DEFAULT_MODELS.get(n, '')}{note}")
        return 0
    if not a.idea:
        print("terai temmo: give a game idea, e.g. terai temmo \"a cat collects fish and runs from a dog\"", file=sys.stderr)
        return 2
    from .pipeline import build
    rep = build(" ".join(a.idea), a.out, roles=over, seed=a.seed, test=not a.no_test, voice=not a.no_voice, mod=not a.no_mod,
                replay=a.replay)
    t = rep.get("test") or {}
    if a.json:
        print(json.dumps({k: rep[k] for k in ("roles", "build", "test", "warnings", "seconds")}, ensure_ascii=False, indent=1))
    else:
        print(f"{rep['gdd']['title']}: {len(rep['gdd']['levels'])} levels -> {rep['build']['html']}")
        if t:
            print(f"test: {'PASS' if t['passed'] else 'FAIL'} result={t.get('result')} cleared={t.get('cleared')} errors={len(t['errors'])}")
    return 0 if (not t or t.get("passed")) else 1
