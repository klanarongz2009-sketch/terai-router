"""Temmo providers: BYOK (bring your own key) adapters + local Gemma + a deterministic mock.

Every cloud adapter is split into ``build_request`` (pure: url, headers, json body) and
``parse_response`` (pure: provider JSON -> text or image bytes), so the wire format is covered
by contract tests without a network call or a key. ``call`` does the HTTP POST with urllib.

Keys are read only from the environment of the person running Temmo (ANTHROPIC_API_KEY,
OPENAI_API_KEY, DEEPSEEK_API_KEY, GEMINI_API_KEY). Temmo never signs up, pays or stores keys.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import urllib.request
from dataclasses import dataclass, field

# Default models (checked against provider docs in Oct 2026; override with --model-<role>).
# Gemini 2.0 Flash was shut down on 2026-06-01 (ai.google.dev/gemini-api/docs/deprecations);
# Google lists gemini-3.6-flash as its replacement, so that is the chat default.
DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-4-5",
    "openai": "gpt-5-mini",
    "deepseek": "deepseek-chat",
    "gemini": "gemini-3.6-flash",
    "gemini-image": "gemini-2.5-flash-image",  # "Nano Banana"
}
ENV_KEYS = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "gemini-image": "GEMINI_API_KEY",
}
# Roles requested by Bogus: game code = Claude + ChatGPT + Nano Banana + DeepSeek; chat = Gemini.
DEFAULT_ROLES = {
    "design": "anthropic",   # game design doc
    "code": "anthropic",     # game code (mod.js)
    "review": "openai",      # second opinion on the design
    "repair": "deepseek",    # fixes code when the headless test fails
    "image": "gemini-image", # sprites / title art (fallback: SANKPUP)
    "chat": "gemini",        # talks with the player about the game
}


class ProviderError(RuntimeError):
    pass


@dataclass
class Request:
    url: str
    headers: dict
    body: dict


@dataclass
class Provider:
    name: str
    model: str = ""
    key: str = ""
    timeout: int = 120
    calls: list = field(default_factory=list)

    kind = "text"

    def build_request(self, system: str, prompt: str, max_tokens: int = 4096) -> Request:
        raise NotImplementedError

    def parse_response(self, data: dict):
        raise NotImplementedError

    def call(self, system: str, prompt: str, max_tokens: int = 4096):
        if not self.key:
            raise ProviderError(f"{self.name}: no key in ${ENV_KEYS.get(self.name, '?')}")
        req = self.build_request(system, prompt, max_tokens)
        http = urllib.request.Request(req.url, data=json.dumps(req.body).encode(), headers=req.headers, method="POST")
        try:
            with urllib.request.urlopen(http, timeout=self.timeout) as r:
                data = json.loads(r.read().decode())
        except urllib.error.HTTPError as e:  # pragma: no cover - network
            raise ProviderError(f"{self.name}: HTTP {e.code} {e.read()[:300]!r}") from e
        self.calls.append({"role_prompt_chars": len(prompt)})
        return self.parse_response(data)

    # text helper used by the pipeline
    def complete(self, system: str, prompt: str, max_tokens: int = 4096) -> str:
        return self.call(system, prompt, max_tokens)


class Anthropic(Provider):
    def build_request(self, system, prompt, max_tokens=4096):
        return Request("https://api.anthropic.com/v1/messages",
                       {"x-api-key": self.key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                       {"model": self.model, "max_tokens": max_tokens, "system": system,
                        "messages": [{"role": "user", "content": prompt}]})

    def parse_response(self, data):
        if data.get("type") == "error":
            raise ProviderError(f"anthropic: {data.get('error')}")
        return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")


class OpenAICompatible(Provider):
    base = "https://api.openai.com/v1"

    def build_request(self, system, prompt, max_tokens=4096):
        return Request(f"{self.base}/chat/completions",
                       {"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"},
                       {"model": self.model, "max_completion_tokens": max_tokens,
                        "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}]})

    def parse_response(self, data):
        if "error" in data:
            raise ProviderError(f"{self.name}: {data['error']}")
        return data["choices"][0]["message"]["content"] or ""


class OpenAI(OpenAICompatible):
    pass


class DeepSeek(OpenAICompatible):
    base = "https://api.deepseek.com"

    def build_request(self, system, prompt, max_tokens=4096):
        r = super().build_request(system, prompt, max_tokens)
        r.body["max_tokens"] = r.body.pop("max_completion_tokens")
        return r


class Gemini(Provider):
    def build_request(self, system, prompt, max_tokens=4096):
        return Request(f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent",
                       {"x-goog-api-key": self.key, "Content-Type": "application/json"},
                       {"systemInstruction": {"parts": [{"text": system}]},
                        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                        "generationConfig": {"maxOutputTokens": max_tokens}})

    def parse_response(self, data):
        if "error" in data:
            raise ProviderError(f"gemini: {data['error']}")
        parts = data["candidates"][0]["content"].get("parts", [])
        return "".join(p.get("text", "") for p in parts)


class GeminiImage(Gemini):
    """Nano Banana: generateContent with an image part in the response."""
    kind = "image"

    def build_request(self, system, prompt, max_tokens=4096):
        r = super().build_request(system, prompt, max_tokens)
        r.body["generationConfig"] = {"responseModalities": ["IMAGE"]}
        return r

    def parse_response(self, data):
        if "error" in data:
            raise ProviderError(f"gemini-image: {data['error']}")
        for p in data["candidates"][0]["content"].get("parts", []):
            inline = p.get("inlineData") or p.get("inline_data")
            if inline and str(inline.get("mimeType", inline.get("mime_type", ""))).startswith("image/"):
                return base64.b64decode(inline["data"])
        raise ProviderError("gemini-image: no image part in response")


class LocalGemma(Provider):
    """Gemma 4 on this machine through SANKPUP's llama.cpp backend (Apache-2.0, no key, no account)."""

    def __init__(self, name="local", model="", **kw):
        super().__init__(name=name, model=model or "gemma-4-E2B", **kw)
        self._backend = None

    def complete(self, system, prompt, max_tokens=2048, seed=7, timeout=600.0):
        from terai_router.sankpup.gemma import GemmaBackend, llama_cpp_available
        if not llama_cpp_available() and os.environ.get("TEMMO_GEMMA_PYTHON"):
            return self._complete_subprocess(system, prompt, max_tokens, seed, timeout)
        if self._backend is None:
            self._backend = GemmaBackend(model=self.model.replace("gemma-4-", "").lower() or "e2b", n_ctx=4096)
        text, usage = self._backend.complete([{"role": "system", "content": system}, {"role": "user", "content": prompt}],
                                             max_tokens=max_tokens, temperature=0.5, seed=seed, timeout=timeout)
        self.calls.append(dict(usage, role_prompt_chars=len(prompt)))
        return text

    def _complete_subprocess(self, system, prompt, max_tokens, seed, timeout):
        """Run Gemma in another Python that has llama-cpp-python ($TEMMO_GEMMA_PYTHON)."""
        import subprocess
        from pathlib import Path
        src = str(Path(__file__).resolve().parents[2])
        code = ("import sys,json; sys.path.insert(0, %r); from terai_router.sankpup.gemma import GemmaBackend; "
                "a=json.load(sys.stdin); b=GemmaBackend(model=a['model'], n_ctx=4096); "
                "t,u=b.complete(a['messages'], max_tokens=a['max_tokens'], temperature=0.5, seed=a['seed'], timeout=a['timeout']); "
                "print(json.dumps({'text': t, 'usage': u}))") % src
        arg = {"model": self.model.replace("gemma-4-", "").lower() or "e2b", "max_tokens": max_tokens, "seed": seed,
               "timeout": timeout, "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}]}
        p = subprocess.run([os.environ["TEMMO_GEMMA_PYTHON"], "-c", code], input=json.dumps(arg), capture_output=True,
                           text=True, timeout=timeout + 300)
        if p.returncode != 0:
            raise ProviderError(f"local gemma failed: {p.stderr[-400:]}")
        out = json.loads(p.stdout.strip().splitlines()[-1])
        self.calls.append(dict(out["usage"], role_prompt_chars=len(prompt)))
        return out["text"]


class Mock(Provider):
    """Deterministic stand-in used by contract tests and --provider mock (no network)."""

    def __init__(self, name="mock", model="mock-1", script=None, **kw):
        super().__init__(name=name, model=model, **kw)
        self.script = script or {}

    def complete(self, system, prompt, max_tokens=4096):
        self.calls.append({"role_prompt_chars": len(prompt)})
        for marker, reply in self.script.items():
            if marker in system or marker in prompt:
                return reply(prompt) if callable(reply) else reply
        h = int(hashlib.sha256(prompt.encode()).hexdigest()[:8], 16)
        return json.dumps({"note": "mock", "hash": h})


CLASSES = {"anthropic": Anthropic, "openai": OpenAI, "deepseek": DeepSeek, "gemini": Gemini, "gemini-image": GeminiImage}


def make(name: str, model: str = "", env=None) -> Provider:
    env = os.environ if env is None else env
    if name == "local":
        return LocalGemma(model=model)
    if name == "mock":
        return Mock()
    if name not in CLASSES:
        raise ProviderError(f"unknown provider {name!r}; choose from {sorted(CLASSES) + ['local', 'mock']}")
    return CLASSES[name](name=name, model=model or DEFAULT_MODELS[name], key=env.get(ENV_KEYS[name], ""))


def resolve_roles(overrides: dict | None = None, env=None, fallback: str = "local") -> dict:
    """Pick a provider per role. A role whose provider has no key falls back (default: local Gemma)."""
    env = os.environ if env is None else env
    roles = dict(DEFAULT_ROLES, **(overrides or {}))
    out = {}
    for role, name in roles.items():
        if name in ("local", "mock") or env.get(ENV_KEYS.get(name, ""), ""):
            out[role] = name
        else:
            out[role] = "sankpup" if role == "image" else fallback
    return out
