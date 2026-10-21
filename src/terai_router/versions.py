"""Version scheme: the repository/package and the models have separate versions (since v0.16.0).

- The package ``terai-router`` keeps 0.X.Y versions. It is not 1.0; the 1.0 criteria for the repository are
  unchanged.
- Each model has its own id. The TER-AI model (chat, tools, image reading) is ``TERAI1BETA``.

``terai --version`` prints both, for example ``terai-router 0.16.0 / model TERAI1BETA``.

Default rule for every model id (TER-AI, MuML, Temmo and later models):

1. A model id is the model's own name and version, written exactly as listed in ``MODELS`` below. It does not
   follow the package version, and a package release does not change any model id.
2. The ids in use keep their current spelling: ``TERAI1BETA``, ``MuML 1.0`` (note writer behind MuML 1.0 WA; trained network ``muml-1.0-net`` since 0.15.0),
   ``MUML 1.0 HIQ`` (text-to-music audio), ``Temmo 1.0`` (game maker), ``TER-AI-0.5`` (TERM AI trial).
3. A new version of one model changes only that model's id and its row here (``since`` = the package version that
   first ships it). The package still moves 0.X.Y as usual.
4. The "1.0" in a model id is not the repository's 1.0. The repository reaches 1.0 only by its own criteria
   (see the Roadmap in README.md), which are unchanged.
"""
from __future__ import annotations

from . import __version__

REPO_VERSION = __version__
MODEL_ID = "TERAI1BETA"
MODEL_ID_RULE = ("model ids are separate from the package version; a package release never changes a model id; "
                 "existing ids keep their spelling (TERAI1BETA, MuML 1.0, MUML 1.0 HIQ, Temmo 1.0, TER-AI-0.5)")

# One row per model the package can run. "since" is the package version that first shipped the model under this id.
MODELS = [
    {"id": "TERAI1BETA", "part": "TER-AI chat and image reading (terai chat, terai vision)", "since": "0.16.0",
     "status": "beta",
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
