"""Tagentic (first version Tagentic1, beta): the TER-AI thinking + agentic model. Prototype, not released.

Tagentic1 runs on the same local Gemma 4 E2B (llama-cpp-python, CPU, offline after the weights are downloaded) as
TERAI1. It works on files in one workspace folder: it lists, reads and searches files, writes and edits them, and
runs Python or shell commands to check its code.

Its thinking is not a long text. Each step is one short line, the tool call it makes, and a short note (written by
code, not by the model) on what came back, for example::

    1. อ่าน config ก่อน → read_file(path="pyproject.toml") → อ่านบรรทัด 1-40 จาก 40

The trace is kept as JSON lines and the final answer is separate from it.

Every run loads four memory files, in this order: ``User.md`` (who the user is), ``Systemprompt.md`` (the prompt
instructions Tagentic1 runs on), ``Memory.md`` (permanent memory; the ``remember`` tool appends durable facts) and
``Systemskill.md`` (system skills, including the ai-memory-continuity skill, NOTICE item 16). ``User.md`` and
``Memory.md`` live in the user's memory folder (``~/.terai/tagentic`` by default) and are never part of this
repository; ``Systemprompt.md`` and ``Systemskill.md`` ship with the package and can be overridden there.

Every reply is the model's own text: no fixed replies, no output filter. A session opens with the model's own
greeting. Identity (Tagentic from TER-AI / Klanarongz2009 on GitHub, not developed by Google) is set by Systemprompt.md
only, so the base model can still sometimes say it was developed by Google.
"""
from .agent import Tagentic, RunResult, parse_step  # noqa: F401
from .cli import MODEL_NAME, Session  # noqa: F401
from .memory import MEMORY_ORDER, default_home, init_home, load_memory  # noqa: F401
from .tools import Toolbox, ToolResult  # noqa: F401
from .trace import Step, Trace  # noqa: F401
from .workspace import SandboxError, Workspace  # noqa: F401
