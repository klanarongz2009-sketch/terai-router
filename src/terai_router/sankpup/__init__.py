"""SANKPUP (from Thai "สร้างภาพ", "make a picture"): images made purely from code.

A prompt (Thai or English) becomes SVG code, written either by a local
Gemma 4 model or by the built-in offline generator.  The SVG is sanitized,
then rendered to PNG (resvg-py or cairosvg) and converted to JPG (Pillow).
No pixel/diffusion model and no cloud API is involved.

    >>> from terai_router.sankpup import generate
    >>> art = generate("แมวสีส้มนั่งบนดวงจันทร์", engine="offline")
    >>> art.engine, art.svg.startswith("<svg")
    ('offline', True)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

from . import gemma, offline
from .render import RenderError, render
from .sanitize import SvgError, sanitize_svg

__all__ = ["Artwork", "generate", "save", "SvgError", "RenderError", "ENGINES"]

ENGINES = ("auto", "gemma", "offline")


@dataclass
class Artwork:
    prompt: str
    svg: str
    engine: str
    model: str | None = None
    seconds: float = 0.0
    fallback_reason: str | None = None
    details: dict = field(default_factory=dict)

    def to_bytes(self, fmt: str = "png", size: int = 512, quality: int = 90) -> bytes:
        return render(self.svg, fmt, size, quality)


def _offline(prompt: str, seed: int, started: float, reason: str | None = None) -> Artwork:
    info = offline.compose(prompt, seed)
    svg, _report = sanitize_svg(info["svg"])
    details = {k: info[k] for k in ("subjects", "scenes", "layout")}
    return Artwork(prompt, svg, "offline", None, round(time.time() - started, 3), reason, details)


def generate(prompt: str, engine: str = "auto", model: str | None = None, seed: int = 0,
             timeout: float = 300.0, attempts: int = 2, fallback: bool = True,
             backend: gemma.GemmaBackend | None = None, **backend_kw) -> Artwork:
    """Turn ``prompt`` into sanitized SVG.

    ``engine``: ``offline`` (rules/templates, instant), ``gemma`` (local Gemma 4
    writes the SVG; downloads weights on first use) or ``auto`` (Gemma only if
    it is installed and its weights are already on disk, else offline).
    With ``fallback`` the offline generator answers if Gemma fails.
    """
    prompt = (prompt or "").strip()
    if not prompt:
        raise ValueError("prompt is empty")
    if engine not in ENGINES:
        raise ValueError(f"engine must be one of {', '.join(ENGINES)}")
    started = time.time()
    if engine == "offline":
        return _offline(prompt, seed, started)
    if engine == "auto" and backend is None:
        server = backend_kw.get("server")
        if not server and not (gemma.llama_cpp_available() and gemma.is_downloaded(model)):
            return _offline(prompt, seed, started)
    if backend is None:
        backend = gemma.GemmaBackend(model=model, auto_download=(engine == "gemma"), **backend_kw)
    try:
        svg, info = gemma.draw_svg(backend, prompt, attempts=attempts, seed=seed or None, timeout=timeout)
    except (gemma.GemmaUnavailable, SvgError, ValueError) as exc:
        if not fallback:
            raise
        return _offline(prompt, seed, started, reason=str(exc))
    return Artwork(prompt, svg, "gemma", backend.label, round(time.time() - started, 3), None, info)


def save(art: Artwork, path: str | Path, fmt: str | None = None, size: int = 512,
         quality: int = 90, save_code: bool = False) -> list[Path]:
    """Write ``art`` to ``path`` (format from ``fmt`` or the extension); optionally the .svg too."""
    path = Path(path)
    fmt = (fmt or path.suffix.lstrip(".") or "png").lower()
    if fmt == "jpeg":
        fmt = "jpg"
    if path.suffix.lower().lstrip(".") not in (fmt, "jpeg" if fmt == "jpg" else fmt):
        path = path.with_suffix("." + fmt)
    data = art.to_bytes(fmt, size, quality)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    written = [path]
    if save_code and fmt != "svg":
        code = path.with_suffix(".svg")
        code.write_text(art.svg, encoding="utf-8")
        written.append(code)
    return written
