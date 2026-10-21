"""Local Gemma 4 backend for SANKPUP: Gemma writes SVG code, nothing is drawn by pixels.

Runtimes (all local, no cloud API):

* ``llama-cpp`` (default): in-process via ``llama-cpp-python`` and Google's
  official QAT Q4_0 GGUF weights, downloaded from Hugging Face on first use
  into ``$TERAI_MODELS_DIR`` (default ``~/.cache/terai/models``) and checked
  against the published SHA-256.
* ``server``: any OpenAI-compatible local server that already serves Gemma 4,
  e.g. ``llama-server`` (``http://127.0.0.1:8080/v1``) or Ollama
  (``http://127.0.0.1:11434/v1`` with ``--server-model gemma4:e2b``).

Gemma 4 weights are released by Google under the Apache License 2.0.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from .sanitize import SvgError, clean_model_output


@dataclass(frozen=True)
class ModelSpec:
    key: str
    repo: str
    filename: str
    size: int
    sha256: str
    note: str

    @property
    def url(self) -> str:
        return f"https://huggingface.co/{self.repo}/resolve/main/{self.filename}"

    @property
    def size_gb(self) -> float:
        return round(self.size / 1e9, 2)


# Official Google QAT Q4_0 GGUF builds (Apache-2.0, not gated on Hugging Face).
MODELS = {
    "e2b": ModelSpec("e2b", "google/gemma-4-E2B-it-qat-q4_0-gguf", "gemma-4-E2B_q4_0-it.gguf", 3349516256,
                     "fa401b55b07ee70a54c6dae3903c783a6e65064312529ea57175cb5f8dec6634",
                     "default; runs on 8 GB RAM, CPU only"),
    "e4b": ModelSpec("e4b", "google/gemma-4-E4B-it-qat-q4_0-gguf", "gemma-4-E4B_q4_0-it.gguf", 5154941280,
                     "676c35070db6dbe52f93e9c864ee0fba4eddea94b9c875d9cb10daff453fbaee",
                     "better drawings, slower; 8 GB RAM is tight"),
    "12b": ModelSpec("12b", "google/gemma-4-12B-it-qat-q4_0-gguf", "gemma-4-12b-it-qat-q4_0.gguf", 6975879296,
                     "93567e57a8fe10b23569b9d9ec38cd005deedf71e29477c421a4b83f418a538b",
                     "needs about 12 GB RAM or a GPU"),
    "26b-a4b": ModelSpec("26b-a4b", "google/gemma-4-26B-A4B-it-qat-q4_0-gguf", "gemma-4-26B_q4_0-it.gguf", 14439363584,
                         "3eca3b8f6d7baf218a7dd6bba5fb59a56ee25fe2d567b6f5f589b4f697eca51d",
                         "MoE; needs about 20 GB RAM or a GPU"),
    "31b": ModelSpec("31b", "google/gemma-4-31B-it-qat-q4_0-gguf", "gemma-4-31B_q4_0-it.gguf", 17651001568,
                     "179cfb99212709597eae5929112cfca677e1bbf566178b479ae1da0c4772874b",
                     "needs about 24 GB RAM or a GPU"),
}
DEFAULT_MODEL = "e2b"

SYSTEM_PROMPT = (
    "You are SANKPUP, an illustrator who draws only by writing SVG code. "
    "Reply with exactly one complete SVG document and nothing else: no markdown, no explanation. "
    'Rules: the root is <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">; '
    "start with a full-size background <rect>; use only rect, circle, ellipse, line, polyline, polygon, "
    "path, g, linearGradient, radialGradient and stop; no text, no image, no script, no style element, "
    "no external links; flat colours; draw every subject the user names so it is recognisable, large "
    "and well placed; use at most 40 shapes. The user may write in Thai or English."
)
RETRY_PROMPT = (
    "That SVG could not be used ({error}). Reply again with one complete, shorter SVG "
    "(at most 25 shapes) that follows every rule."
)


class GemmaUnavailable(RuntimeError):
    """Raised when the local Gemma runtime or weights are missing."""


INSTALL_HINT = (
    'The Gemma engine needs an optional extra: pip install "terai-router[sankpup-gemma]" '
    "(llama-cpp-python), or point --server at a local llama-server/Ollama that serves Gemma 4."
)


def models_dir() -> Path:
    env = os.environ.get("TERAI_MODELS_DIR")
    return Path(env).expanduser() if env else Path.home() / ".cache" / "terai" / "models"


def resolve_model(model: str | None) -> tuple[ModelSpec | None, Path]:
    """Map a variant key (e2b, e4b, ...) or a .gguf path to (spec, local path)."""
    model = (model or DEFAULT_MODEL).strip()
    key = model.lower().replace("gemma-4-", "").replace("gemma4:", "")
    if key in MODELS:
        spec = MODELS[key]
        return spec, models_dir() / spec.filename
    path = Path(model).expanduser()
    if path.suffix.lower() == ".gguf":
        return None, path
    raise ValueError(f"unknown Gemma 4 model '{model}' (choose {', '.join(MODELS)} or a .gguf path)")


def is_downloaded(model: str | None = None) -> bool:
    try:
        _spec, path = resolve_model(model)
    except ValueError:
        return False
    return path.is_file()


def llama_cpp_available() -> bool:
    try:
        import llama_cpp  # noqa: F401
    except Exception:
        return False
    return True


def download(model: str | None = None, quiet: bool = False, opener=urllib.request.urlopen) -> Path:
    """Download official weights (resumable) and verify SHA-256."""
    spec, path = resolve_model(model)
    if spec is None:
        if not path.is_file():
            raise GemmaUnavailable(f"model file not found: {path}")
        return path
    if path.is_file():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(path.name + ".part")
    have = part.stat().st_size if part.exists() else 0
    req = urllib.request.Request(spec.url, headers={"User-Agent": "terai-router-sankpup"})
    if have:
        req.add_header("Range", f"bytes={have}-")
    if not quiet:
        print(f"Downloading Gemma 4 {spec.key} ({spec.size_gb} GB) from {spec.url}", file=sys.stderr)
    try:
        resp = opener(req, timeout=60)
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise GemmaUnavailable(
                f"Hugging Face refused the download (HTTP {exc.code}). Open https://huggingface.co/{spec.repo}, "
                "accept the terms if asked, then set HF_TOKEN or download the file yourself and pass --model <path>."
            ) from exc
        raise
    mode = "ab" if have and getattr(resp, "status", 200) == 206 else "wb"
    done = have if mode == "ab" else 0
    last = time.time()
    with resp, open(part, mode) as fh:
        while True:
            chunk = resp.read(1 << 20)
            if not chunk:
                break
            fh.write(chunk)
            done += len(chunk)
            if not quiet and time.time() - last > 5:
                print(f"  {done / 1e9:.2f} / {spec.size_gb} GB", file=sys.stderr)
                last = time.time()
    digest = sha256_file(part)
    if digest != spec.sha256:
        part.unlink(missing_ok=True)
        raise GemmaUnavailable(f"SHA-256 mismatch for {spec.filename}: got {digest}, expected {spec.sha256}")
    part.replace(path)
    return path


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class GemmaBackend:
    """Chat-completion client for a local Gemma 4 (llama-cpp-python or a local server)."""

    def __init__(self, model: str | None = None, server: str | None = None, server_model: str | None = None,
                 threads: int | None = None, n_ctx: int = 4096, auto_download: bool = True, client=None) -> None:
        self.model = model or DEFAULT_MODEL
        self.server = server.rstrip("/") if server else None
        self.server_model = server_model
        self.threads = threads or max(1, os.cpu_count() or 1)
        self.n_ctx = n_ctx
        self.auto_download = auto_download
        self._client = client  # injectable for tests: callable(messages, **kw) -> (text, usage)
        self._llm = None

    @property
    def label(self) -> str:
        if self.server:
            return f"gemma4 via {self.server} ({self.server_model or 'default'})"
        return f"gemma-4-{self.model}"

    def _load(self):
        if self._llm is not None:
            return self._llm
        try:
            from llama_cpp import Llama
        except Exception as exc:
            raise GemmaUnavailable(INSTALL_HINT) from exc
        spec, path = resolve_model(self.model)
        if not path.is_file():
            if not self.auto_download:
                raise GemmaUnavailable(f"Gemma 4 weights not found at {path}; run: terai sankpup --pull {self.model}")
            path = download(self.model)
        self._llm = Llama(model_path=str(path), n_ctx=self.n_ctx, n_threads=self.threads, verbose=False)
        return self._llm

    def complete(self, messages: list, max_tokens: int = 1500, temperature: float = 0.4,
                 seed: int | None = None, timeout: float = 300.0) -> tuple[str, dict]:
        if self._client is not None:
            return self._client(messages, max_tokens=max_tokens, temperature=temperature, seed=seed, timeout=timeout)
        if self.server:
            return self._complete_server(messages, max_tokens, temperature, seed, timeout)
        return self._complete_local(messages, max_tokens, temperature, seed, timeout)

    def _complete_local(self, messages, max_tokens, temperature, seed, timeout):
        llm = self._load()
        start = time.time()
        parts = []
        tokens = 0
        timed_out = False
        kwargs = {"messages": messages, "max_tokens": max_tokens, "temperature": temperature,
                  "stop": ["</svg>"], "stream": True}
        if seed is not None:
            kwargs["seed"] = seed
        for chunk in llm.create_chat_completion(**kwargs):
            delta = chunk["choices"][0].get("delta", {}).get("content")
            if delta:
                parts.append(delta)
                tokens += 1
            if time.time() - start > timeout:
                timed_out = True
                break
        text = "".join(parts)
        if "<svg" in text and "</svg>" not in text and not timed_out:
            text += "</svg>"
        return text, {"completion_tokens": tokens, "seconds": round(time.time() - start, 2), "timed_out": timed_out}

    def _complete_server(self, messages, max_tokens, temperature, seed, timeout):
        body = {"messages": messages, "max_tokens": max_tokens, "temperature": temperature, "stop": ["</svg>"]}
        if self.server_model:
            body["model"] = self.server_model
        if seed is not None:
            body["seed"] = seed
        req = urllib.request.Request(self.server + "/chat/completions", data=json.dumps(body).encode("utf-8"),
                                     headers={"Content-Type": "application/json"})
        start = time.time()
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise GemmaUnavailable(f"local Gemma server at {self.server} did not answer: {exc}") from exc
        text = data["choices"][0]["message"].get("content") or ""
        if "<svg" in text and "</svg>" not in text:
            text += "</svg>"
        usage = data.get("usage", {})
        return text, {"completion_tokens": usage.get("completion_tokens"), "seconds": round(time.time() - start, 2), "timed_out": False}


def draw_svg(backend: GemmaBackend, prompt: str, size: int | None = None, attempts: int = 2,
             seed: int | None = None, timeout: float = 300.0, max_tokens: int = 1500) -> tuple[str, dict]:
    """Ask Gemma for SVG, sanitize it, retry with the error message when it is unusable."""
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}]
    log = []
    deadline = time.time() + timeout
    for attempt in range(1, max(1, attempts) + 1):
        left = deadline - time.time()
        if left <= 1:
            break
        text, usage = backend.complete(messages, max_tokens=max_tokens, temperature=0.4 if attempt == 1 else 0.2,
                                       seed=seed, timeout=left)
        entry = {"attempt": attempt, **usage}
        try:
            svg, report = clean_model_output(text, size)
        except SvgError as exc:
            entry["error"] = str(exc)
            log.append(entry)
            messages = messages[:2] + [{"role": "assistant", "content": text[-4000:]},
                                       {"role": "user", "content": RETRY_PROMPT.format(error=exc)}]
            continue
        entry.update(repaired=report["repaired"], removed_elements=report["removed_elements"],
                     removed_attributes=report["removed_attributes"], shapes=report["drawn"])
        log.append(entry)
        return svg, {"attempts": log, "model": backend.label}
    raise SvgError("Gemma did not produce usable SVG: " + "; ".join(e.get("error", "timeout") for e in log) if log
                   else "Gemma timed out before producing SVG")
