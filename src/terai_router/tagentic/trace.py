"""The Tagentic1 thinking trace: one short line + one tool call + a short note per step, as JSON lines."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field

THINK_MAX = 120   # characters kept from the model's thinking line
NOTE_MAX = 120


def shorten(text: str, limit: int) -> str:
    t = ' '.join(str(text or '').split())
    return t if len(t) <= limit else t[:limit - 1].rstrip() + '…'


def arg_summary(args: dict) -> str:
    """Compact view of tool arguments: short values in full, long ones as their size."""
    parts = []
    for k, v in (args or {}).items():
        if isinstance(v, str):
            if len(v) > 40 or '\n' in v:
                parts.append(f'{k}=<{len(v.encode("utf-8"))} bytes>')
            else:
                parts.append(f'{k}={json.dumps(v, ensure_ascii=False)}')
        else:
            s = json.dumps(v, ensure_ascii=False)
            parts.append(f'{k}={s if len(s) <= 40 else s[:37] + "..."}')
    return ', '.join(parts)


@dataclass
class Step:
    step: int
    think: str
    tool: str
    args: dict = field(default_factory=dict)
    ok: bool = True
    note: str = ''
    ms: int = 0

    def to_dict(self) -> dict:
        return asdict(self)

    def compact(self) -> str:
        return f'{self.step}. {self.think} → {self.tool}({arg_summary(self.args)}) → {self.note}'


@dataclass
class Trace:
    steps: list = field(default_factory=list)
    final: str = ''
    stopped: str = ''      # answer | max_steps | timeout | error
    seconds: float = 0.0

    def add(self, step: Step) -> Step:
        self.steps.append(step)
        return step

    def jsonl(self) -> str:
        lines = [json.dumps(s.to_dict(), ensure_ascii=False) for s in self.steps]
        lines.append(json.dumps({'final': self.final, 'steps': len(self.steps), 'stopped': self.stopped,
                                 'seconds': round(self.seconds, 2)}, ensure_ascii=False))
        return '\n'.join(lines) + '\n'

    def compact(self) -> str:
        return '\n'.join(s.compact() for s in self.steps)

    def write(self, path: str) -> None:
        with open(path, 'a', encoding='utf-8') as fh:
            fh.write(self.jsonl())

    @staticmethod
    def read(path: str) -> list:
        with open(path, encoding='utf-8') as fh:
            return [json.loads(x) for x in fh if x.strip()]
