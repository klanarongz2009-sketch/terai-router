"""``terai sankpup``: make PNG/JPG/SVG images from code."""

from __future__ import annotations

import argparse
import json
import sys

from . import ENGINES, RenderError, SvgError, gemma, generate, save
from .render import MAX_SIZE, MIN_SIZE, available_renderers


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="terai sankpup",
        description="SANKPUP: images drawn purely from code. Local Gemma 4 (or the offline generator) "
                    "writes SVG, which is sanitized and rendered to PNG/JPG. No cloud API.",
    )
    ap.add_argument("prompt", nargs="*", help="what to draw, in Thai or English; '-' reads it from stdin")
    ap.add_argument("-o", "--out", default="sankpup.png", help="output file (default: sankpup.png)")
    ap.add_argument("--format", choices=("png", "jpg", "svg"), help="output format (default: from --out extension)")
    ap.add_argument("--size", type=int, default=512, help=f"square image size in pixels ({MIN_SIZE}-{MAX_SIZE}, default 512)")
    ap.add_argument("--quality", type=int, default=90, help="JPG quality 1-95 (default 90)")
    ap.add_argument("--engine", choices=ENGINES, default="auto",
                    help="gemma = local Gemma 4; offline = built-in rules; auto = gemma if installed and downloaded")
    ap.add_argument("--model", default=gemma.DEFAULT_MODEL,
                    help=f"Gemma 4 variant ({', '.join(gemma.MODELS)}) or a .gguf path (default {gemma.DEFAULT_MODEL})")
    ap.add_argument("--server", metavar="URL", help="use a local OpenAI-compatible server (llama-server, Ollama) instead of llama-cpp-python")
    ap.add_argument("--server-model", metavar="NAME", help="model name for --server, e.g. gemma4:e2b for Ollama")
    ap.add_argument("--threads", type=int, help="CPU threads for llama-cpp-python (default: all cores)")
    ap.add_argument("--timeout", type=float, default=300.0, help="seconds allowed for Gemma, retries included (default 300)")
    ap.add_argument("--attempts", type=int, default=2, help="Gemma tries before falling back (default 2)")
    ap.add_argument("--no-fallback", action="store_true", help="fail instead of using the offline generator when Gemma fails")
    ap.add_argument("--seed", type=int, default=0, help="seed for repeatable output")
    ap.add_argument("--save-code", action="store_true", help="also write the sanitized .svg next to the image")
    ap.add_argument("--json", action="store_true", help="print a JSON report")
    ap.add_argument("--pull", metavar="MODEL", nargs="?", const=gemma.DEFAULT_MODEL,
                    help="download Gemma 4 weights (default e2b) and exit")
    ap.add_argument("--list-models", action="store_true", help="list Gemma 4 variants and exit")
    return ap


def _list_models() -> None:
    print(f"models dir: {gemma.models_dir()}")
    print(f"llama-cpp-python: {'installed' if gemma.llama_cpp_available() else 'not installed'}")
    renderers = ", ".join(available_renderers()) or 'none (pip install "terai-router[sankpup]")'
    print(f"renderers: {renderers}")
    for key, spec in gemma.MODELS.items():
        mark = "downloaded" if gemma.is_downloaded(key) else "-"
        default = " (default)" if key == gemma.DEFAULT_MODEL else ""
        print(f"  {key:<8} {spec.size_gb:>5} GB  {mark:<10} {spec.note}{default}")
    print("Gemma 4 weights: Google, Apache License 2.0.")


def main(argv=None) -> int:
    a = build_parser().parse_args(argv)
    if a.list_models:
        _list_models()
        return 0
    if a.pull:
        try:
            path = gemma.download(a.pull)
        except (gemma.GemmaUnavailable, ValueError) as exc:
            print(f"terai sankpup: {exc}", file=sys.stderr)
            return 2
        print(path)
        return 0
    prompt = " ".join(a.prompt).strip()
    if prompt == "-":
        prompt = sys.stdin.read().strip()
    if not prompt:
        print("terai sankpup: give a prompt, e.g. terai sankpup \"แมวสีส้มนั่งบนดวงจันทร์\" -o cat.png", file=sys.stderr)
        return 2
    if not MIN_SIZE <= a.size <= MAX_SIZE:
        print(f"terai sankpup: --size must be between {MIN_SIZE} and {MAX_SIZE}", file=sys.stderr)
        return 2
    kw = {}
    if a.server:
        kw.update(server=a.server, server_model=a.server_model)
    if a.threads:
        kw["threads"] = a.threads
    try:
        art = generate(prompt, engine=a.engine, model=a.model, seed=a.seed, timeout=a.timeout,
                       attempts=a.attempts, fallback=not a.no_fallback, **kw)
        files = save(art, a.out, a.format, a.size, a.quality, a.save_code)
    except (SvgError, RenderError, gemma.GemmaUnavailable, ValueError) as exc:
        print(f"terai sankpup: {exc}", file=sys.stderr)
        return 1
    if a.json:
        print(json.dumps({"prompt": art.prompt, "engine": art.engine, "model": art.model, "seconds": art.seconds,
                          "fallback_reason": art.fallback_reason, "files": [str(f) for f in files],
                          "details": art.details}, ensure_ascii=False, indent=2))
    else:
        note = f" (fallback: {art.fallback_reason})" if art.fallback_reason else ""
        who = art.model or "offline generator"
        print(f"{', '.join(str(f) for f in files)}  [{art.engine}: {who}, {art.seconds}s]{note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
