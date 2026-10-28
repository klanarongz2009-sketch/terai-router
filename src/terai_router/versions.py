"""Version scheme: the repository/package and the models have separate versions (since v0.16.0).

- The package ``terai-router`` keeps 0.X.Y versions. It is not 1.0; the 1.0 criteria for the repository are
  unchanged.
- Each model has its own id. The TER-AI model (chat, tools, image reading) is ``TERAI1`` (beta). It was
  ``TERAI1BETA`` in 0.16.0; that name still works as an alias and prints a deprecation notice.

``terai --version`` prints both, for example ``terai-router 0.17.0 / model TERAI1``.

Default rule for every model id (TER-AI, MuML, Temmo and later models):

1. A model id is the model's own name and version, written exactly as listed in ``MODELS`` below. It does not
   follow the package version, and a package release does not change any model id.
2. The ids in use keep their current spelling: ``TERAI1``, ``MuML 1.0`` (note writer behind MuML 1.0 WA; trained network ``muml-1.0-net`` since 0.15.0),
   ``MUML 1.0 HIQ`` (text-to-music audio), ``Temmo 1.0`` (game maker), ``TER-AI-0.5`` (TERM AI trial).
   Exception (0.17.0, approved by the maintainer): ``TERAI1BETA`` was renamed to ``TERAI1``. "BETA" only marked
   the status, which now lives in the ``status`` field. The old spelling stays a working alias
   (``MODEL_ID_ALIASES``, ``--brain terai1beta``, ``--engine terai1beta``) that prints a deprecation notice.
   Its ``since`` stays 0.16.0 because it is the same model. This is the only rename; it does not change the
   rule for any other id.
3. A new version of one model changes only that model's id and its row here (``since`` = the package version that
   first ships it). The package still moves 0.X.Y as usual.
4. The "1.0" in a model id is not the repository's 1.0. The repository reaches 1.0 only by its own criteria
   (see the Roadmap in README.md), which are unchanged.
"""
from __future__ import annotations

from . import __version__

REPO_VERSION = __version__
MODEL_ID = "TERAI1"
MODEL_ID_RULE = ("model ids are separate from the package version; a package release never changes a model id; "
                 "existing ids keep their spelling (TERAI1, MuML 1.0, MUML 1.0 HIQ, Temmo 1.0, TER-AI-0.5); "
                 "one exception: TERAI1BETA was renamed to TERAI1 in 0.17.0 and stays an alias")

# Old names that still work (0.17.0). Model id alias -> id, and CLI engine name alias -> engine name.
MODEL_ID_ALIASES = {"TERAI1BETA": "TERAI1"}
ENGINE_ALIASES = {"terai1beta": "terai1"}


def deprecation_notice(old: str, new: str) -> str:
    return f"note: '{old}' is deprecated since 0.17.0, use '{new}' (TERAI1BETA was renamed to TERAI1)"


def resolve_model_id(name: str) -> str:
    """Return the current model id for ``name`` (an id or an old alias such as TERAI1BETA)."""
    return MODEL_ID_ALIASES.get(name, MODEL_ID_ALIASES.get(name.upper(), name))


def resolve_engine(name: str, warn: bool = True) -> str:
    """Map an engine name to the current one: ``terai1beta`` -> ``terai1`` (prints a deprecation notice to stderr)."""
    new = ENGINE_ALIASES.get(name)
    if new is None:
        return name
    if warn:
        import sys
        print(deprecation_notice(name, new), file=sys.stderr)
    return new

# One row per model the package can run. "since" is the package version that first shipped the model under this id.
MODELS = [
    {"id": "TERAI1", "part": "TER-AI chat and image reading (terai chat, terai vision)", "since": "0.16.0",
     "status": "beta", "aliases": ["TERAI1BETA"],
     "note": "named TERAI1BETA in 0.16.0; renamed to TERAI1 in 0.17.0 (same model)",
     "made_of": "local Gemma 4 E2B (Apache-2.0) writes the replies and reads images; the TER-AI rules (calculator, "
                "date and time, units, memory, Thai Wikipedia pack, web search) are its tools; a grounding check "
                "falls back to the rule answer; intent router model.json (trained here)"},
    {"id": "MuML 1.0", "part": "music notes (terai muml-wa, web demo MuML tab); network writer muml-1.0-net since 0.15.0",
     "since": "0.12.0",
     "status": "released",
     "made_of": "note table from the Nottingham Music Database (GPL-3.0); network weights trained here"},
    {"id": "MUML 1.0 HIQ", "part": "text-to-music audio (terai muml --hiq)", "since": "0.13.0",
     "status": "released", "made_of": "ACE-Step 1.5 and YuE2-3B run locally (downloaded by --setup)"},
    {"id": "Temmo 1.0", "part": "game maker (terai temmo, web demo Temmo tab)", "since": "-",
     "status": "prototype, not released", "made_of": "local Gemma 4 or an API model writes the game"},
    {"id": "TER-AI-0.5", "part": "TERM AI trial (terai term)", "since": "0.14.0",
     "status": "legacy, removed 2027-01-01", "made_of": "character n-gram Naive Bayes, 11 intents"},
]


def version_line() -> str:
    return f"terai-router {REPO_VERSION} / model {MODEL_ID}"


def models_table() -> str:
    rows = [("model", "part", "since", "status")] + [(m["id"], m["part"], m["since"], m["status"]) for m in MODELS]
    w = [max(len(r[i]) for r in rows) for i in range(4)]
    out = [version_line(), ""]
    for r in rows:
        out.append("  ".join(c.ljust(w[i]) for i, c in enumerate(r)).rstrip())
    return "\n".join(out)
