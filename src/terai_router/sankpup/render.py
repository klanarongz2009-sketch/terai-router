"""Render SVG code to PNG (cairosvg or resvg-py) and convert to JPG (Pillow)."""

from __future__ import annotations

import io

MIN_SIZE = 16
MAX_SIZE = 4096


class RenderError(RuntimeError):
    """Raised when no renderer is installed or rendering fails."""


INSTALL_HINT = (
    'Rendering needs an optional extra: pip install "terai-router[sankpup]" '
    "(installs resvg-py and Pillow; cairosvg also works if it is installed)."
)


def available_renderers() -> list[str]:
    found = []
    try:
        import resvg_py  # noqa: F401
        found.append("resvg")
    except Exception:
        pass
    try:
        import cairosvg  # noqa: F401
        found.append("cairosvg")
    except Exception:
        pass
    return found


def check_size(size: int) -> int:
    size = int(size)
    if not MIN_SIZE <= size <= MAX_SIZE:
        raise ValueError(f"size must be between {MIN_SIZE} and {MAX_SIZE} pixels")
    return size


def svg_to_png(svg: str, size: int = 512, renderer: str | None = None) -> bytes:
    """Rasterise ``svg`` to a ``size`` x ``size`` PNG."""
    size = check_size(size)
    order = [renderer] if renderer else ["resvg", "cairosvg"]
    errors = []
    for name in order:
        try:
            if name == "resvg":
                import resvg_py
                data = resvg_py.svg_to_bytes(svg_string=svg, width=size, height=size)
                return bytes(data)
            if name == "cairosvg":
                import cairosvg
                return cairosvg.svg2png(bytestring=svg.encode("utf-8"), output_width=size, output_height=size, unsafe=False)
            raise RenderError(f"unknown renderer: {name}")
        except ImportError:
            errors.append(f"{name}: not installed")
        except RenderError:
            raise
        except Exception as exc:  # renderer-specific failures
            errors.append(f"{name}: {exc}")
    if all(e.endswith("not installed") for e in errors):
        raise RenderError(INSTALL_HINT)
    raise RenderError("could not render SVG (" + "; ".join(errors) + ")")


def png_to_jpg(png: bytes, quality: int = 90, background: str = "#ffffff") -> bytes:
    """Convert PNG bytes to JPG, flattening transparency onto ``background``."""
    try:
        from PIL import Image
    except ImportError as exc:
        raise RenderError(INSTALL_HINT) from exc
    img = Image.open(io.BytesIO(png))
    img.load()
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        rgba = img.convert("RGBA")
        flat = Image.new("RGB", rgba.size, background)
        flat.paste(rgba, mask=rgba.split()[-1])
        img = flat
    else:
        img = img.convert("RGB")
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=max(1, min(95, int(quality))), optimize=True)
    return out.getvalue()


def render(svg: str, fmt: str = "png", size: int = 512, quality: int = 90) -> bytes:
    fmt = fmt.lower()
    if fmt == "svg":
        return svg.encode("utf-8")
    png = svg_to_png(svg, size)
    if fmt == "png":
        return png
    if fmt in ("jpg", "jpeg"):
        return png_to_jpg(png, quality)
    raise ValueError(f"unsupported format: {fmt} (use png, jpg or svg)")
