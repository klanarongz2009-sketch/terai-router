"""Sanitize and repair SVG code written by a model.

Only a small allow-list of drawing elements and presentation attributes
survives.  Scripts, event handlers, ``foreignObject``, external references,
``<image>``, ``<use>``, CSS ``url()`` to anything but a local ``#id``,
DOCTYPE/ENTITY declarations and oversize documents are rejected or dropped.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

SVG_NS = "http://www.w3.org/2000/svg"
MAX_SVG_BYTES = 200_000
MAX_ELEMENTS = 2_000
MAX_DEPTH = 24

ALLOWED_ELEMENTS = {
    "svg", "g", "defs", "title", "desc", "path", "rect", "circle", "ellipse",
    "line", "polyline", "polygon", "text", "tspan", "linearGradient",
    "radialGradient", "stop", "clipPath", "mask", "pattern",
}
ALLOWED_ATTRS = {
    "id", "x", "y", "x1", "y1", "x2", "y2", "cx", "cy", "r", "rx", "ry", "fx", "fy",
    "width", "height", "d", "points", "viewBox", "preserveAspectRatio",
    "fill", "fill-opacity", "fill-rule", "stroke", "stroke-width", "stroke-opacity",
    "stroke-linecap", "stroke-linejoin", "stroke-dasharray", "stroke-dashoffset",
    "stroke-miterlimit", "opacity", "transform", "offset", "stop-color", "stop-opacity",
    "gradientUnits", "gradientTransform", "spreadMethod", "clip-path", "clip-rule",
    "clipPathUnits", "mask", "maskUnits", "maskContentUnits", "patternUnits",
    "patternContentUnits", "patternTransform", "font-size", "font-family",
    "font-weight", "font-style", "text-anchor", "dominant-baseline", "letter-spacing",
    "dx", "dy", "rotate", "style", "visibility", "display", "version",
}
STYLE_PROPS = {
    "fill", "fill-opacity", "fill-rule", "stroke", "stroke-width", "stroke-opacity",
    "stroke-linecap", "stroke-linejoin", "stroke-dasharray", "opacity", "stop-color",
    "stop-opacity", "font-size", "font-family", "font-weight", "font-style",
    "text-anchor", "display", "visibility",
}
_DOCTYPE = re.compile(r"<!\s*(DOCTYPE|ENTITY|ELEMENT|ATTLIST)", re.I)
_URL = re.compile(r"url\(\s*(['\"]?)(.*?)\1\s*\)", re.I)
_BAD_VALUE = re.compile(r"javascript:|data:|vbscript:|expression\s*\(|@import|<|>", re.I)
_FENCE = re.compile(r"```(?:svg|xml|html)?\s*(.*?)```", re.S | re.I)
_SVG_BLOCK = re.compile(r"<svg\b.*?</svg\s*>", re.S | re.I)
_SVG_OPEN = re.compile(r"<svg\b.*", re.S | re.I)
_TAG = re.compile(r"<(/?)([A-Za-z][\w:.-]*)([^<>]*?)(/?)>", re.S)


class SvgError(ValueError):
    """Raised when SVG code cannot be made safe and valid."""


def extract_svg(text: str) -> str:
    """Pull the first ``<svg>...</svg>`` out of a model reply."""
    text = text or ""
    fence = _FENCE.search(text)
    if fence and "<svg" in fence.group(1).lower():
        text = fence.group(1)
    block = _SVG_BLOCK.search(text)
    if block:
        return block.group(0).strip()
    opened = _SVG_OPEN.search(text)
    if opened:
        return opened.group(0).strip()
    raise SvgError("no <svg> element in the reply")


def repair_svg(code: str) -> str:
    """Best-effort fix for truncated SVG: drop a cut-off last tag, close open tags."""
    code = code.strip()
    cut = code.rfind("<")
    if cut > code.rfind(">"):
        code = code[:cut]
    stack = []
    for m in _TAG.finditer(code):
        closing, name, _attrs, selfclose = m.groups()
        if selfclose or name.startswith(("?", "!")):
            continue
        if closing:
            if name in stack:
                while stack and stack[-1] != name:
                    stack.pop()
                stack.pop()
        else:
            stack.append(name)
    for name in reversed(stack):
        code += f"</{name}>"
    return code


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


_UNCLOSED_LOCAL_URL = re.compile(r"\s*url\(\s*(['\"]?)#[\w.:-]+\1\s*", re.I)


def fix_url(value: str) -> str:
    """Close a local paint reference the model left open: ``url(#g`` -> ``url(#g)``.

    Renderers treat the broken value as invalid paint and fall back to black,
    which can turn a whole picture black (seen in the Gemma 4 E2B bench).
    """
    if _UNCLOSED_LOCAL_URL.fullmatch(value):
        return value.strip() + ")"
    return value


def _safe_value(name: str, value: str) -> bool:
    if _BAD_VALUE.search(value):
        return False
    matches = list(_URL.finditer(value))
    if len(matches) != len(re.findall(r"url\(", value, re.I)):
        return False  # an unterminated url( that could hide an external reference
    for m in matches:
        if not m.group(2).startswith("#"):
            return False
    return True


def _clean_style(value: str) -> str:
    keep = []
    for decl in value.split(";"):
        if ":" not in decl:
            continue
        prop, val = (part.strip() for part in decl.split(":", 1))
        val = fix_url(val)
        if prop.lower() in STYLE_PROPS and val and _safe_value(prop, val):
            keep.append(f"{prop.lower()}:{val}")
    return ";".join(keep)


def sanitize_svg(code: str, size: int | None = None) -> tuple[str, dict]:
    """Return ``(safe_svg, report)``; raise :class:`SvgError` if unusable."""
    if not code or not code.strip():
        raise SvgError("empty SVG")
    raw = code.encode("utf-8")
    if len(raw) > MAX_SVG_BYTES:
        raise SvgError(f"SVG is {len(raw)} bytes (limit {MAX_SVG_BYTES})")
    if _DOCTYPE.search(code):
        raise SvgError("DOCTYPE/ENTITY declarations are not allowed")
    try:
        root = ET.fromstring(code)
    except ET.ParseError as exc:
        raise SvgError(f"invalid XML: {exc}") from exc
    if _local(root.tag) != "svg":
        raise SvgError("root element is not <svg>")

    report = {"removed_elements": 0, "removed_attributes": 0, "elements": 0, "drawn": 0}

    def walk(el: ET.Element, depth: int) -> ET.Element:
        name = _local(el.tag)
        out = ET.Element(name)
        for key, value in el.attrib.items():
            attr = _local(key)
            if key.startswith("{") and attr != "href":
                report["removed_attributes"] += 1
                continue
            if attr == "href" and name in ("linearGradient", "radialGradient", "pattern") and value.startswith("#"):
                out.set("href", value)
                continue
            if attr not in ALLOWED_ATTRS or attr.lower().startswith("on"):
                report["removed_attributes"] += 1
                continue
            if attr == "style":
                value = _clean_style(value)
                if not value:
                    report["removed_attributes"] += 1
                    continue
            elif not _safe_value(attr, value := fix_url(value)):
                report["removed_attributes"] += 1
                continue
            out.set(attr, value)
        if el.text and name in ("title", "desc", "text", "tspan"):
            out.text = el.text
        for child in el:
            cname = _local(child.tag)
            if cname not in ALLOWED_ELEMENTS or depth + 1 > MAX_DEPTH:
                report["removed_elements"] += 1
            else:
                report["elements"] += 1
                if report["elements"] > MAX_ELEMENTS:
                    raise SvgError(f"more than {MAX_ELEMENTS} elements")
                if cname in ("path", "rect", "circle", "ellipse", "line", "polyline", "polygon", "text"):
                    report["drawn"] += 1
                node = walk(child, depth + 1)
                if child.tail and name in ("text", "tspan"):
                    node.tail = child.tail
                out.append(node)
        return out

    clean = walk(root, 0)
    if report["drawn"] == 0:
        raise SvgError("SVG draws nothing")
    if not clean.get("viewBox"):
        w = _num(clean.get("width")) or 512
        h = _num(clean.get("height")) or 512
        clean.set("viewBox", f"0 0 {w:g} {h:g}")
    if size:
        clean.set("width", str(size))
        clean.set("height", str(size))
    elif not clean.get("width"):
        clean.set("width", "512")
        clean.set("height", "512")
    clean.set("xmlns", SVG_NS)
    text = ET.tostring(clean, encoding="unicode", short_empty_elements=True)
    return text, report


def _num(value) -> float:
    if not value:
        return 0.0
    m = re.match(r"\s*([0-9.]+)", str(value))
    try:
        return float(m.group(1)) if m else 0.0
    except ValueError:
        return 0.0


def clean_model_output(text: str, size: int | None = None) -> tuple[str, dict]:
    """extract -> sanitize, falling back to repair once. Report says which."""
    code = extract_svg(text)
    try:
        svg, report = sanitize_svg(code, size)
        report["repaired"] = False
        return svg, report
    except SvgError as first:
        fixed = repair_svg(code)
        if fixed == code:
            raise
        try:
            svg, report = sanitize_svg(fixed, size)
        except SvgError:
            raise first
        report["repaired"] = True
        return svg, report
