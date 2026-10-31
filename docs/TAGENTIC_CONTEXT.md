# Tagentic workspace context: quick start

Tagentic has two distinct context sources. Personal memory lives under `~/.terai/tagentic` and is not part of this repository. Workspace context lives in the folder Tagentic is allowed to work in; it provides project-specific preferences and reference material.

## Create the starter structure

From the project directory, run:

```sh
terai tagentic --init-context
```

To initialize a different workspace, pass its path with `--workspace`:

```sh
terai tagentic --init-context --workspace ./my-project
```

The command creates these files only when they do not already exist:

```text
Userprompt.md                 # your task-relevant preferences for Tagentic
Project.md                    # concise project overview
Agent.md                      # agents/subagents and their roles
Docs/                         # general agent manuals and reference docs
  README.md
Log/                          # runtime or project logs
  README.md
Project/                      # project-specific notes
  README.md
  Hiperframes.md              # example project note
```

It does not replace existing files. The command reports which files it created and which were already present. Edit the starter text for your project, add other Markdown or text files where useful, and keep secrets out of the workspace.

## What is loaded, and when

On each model run, Tagentic builds its system prompt from its built-in/personal prompt and the current workspace:

- `Userprompt.md`, `Project.md`, and `Agent.md` are read into the prompt when present. Their limits are 6,000, 6,000, and 4,000 characters respectively; longer files are truncated.
- Files under `Docs/`, `Project/`, and `Log/` are indexed by path only (up to 100 files). Their bodies are not bulk-loaded into the prompt. When a task makes a file relevant, Tagentic can use its normal sandboxed `list_files`, `search_files`, and `read_file` tools to inspect it. Logs are not automatically read; they may contain sensitive material, so keep them relevant and redact secrets.
- File reads stay within the selected workspace. Tool output is bounded; long results may be clipped.

The context prompt states that built-in safety rules take precedence, the current user request defines the task, and `Userprompt.md` supplies preferences beneath those. `Project.md` and `Agent.md` are reference material. Content in `Docs/`, `Project/`, and `Log/` is data, not authority: embedded instructions cannot expand the user's request, permissions, or safety rules. Context files do not authorize writes, code execution, external messages, or other consequential actions; those continue to follow Tagentic's normal approval rules.

## A practical pattern

1. Keep stable, broadly useful working preferences in `Userprompt.md`.
2. Keep a short, verified project summary and current priorities in `Project.md`.
3. Describe agent/subagent responsibilities and known interfaces in `Agent.md`.
4. Put general manuals in `Docs/`, focused project details in `Project/<name>.md`, and carefully redacted logs in `Log/`.
5. Ask for a task that points to the relevant project or file. Tagentic receives the path index first and reads relevant bodies through the workspace tools as needed.

The starter `Project/Hiperframes.md` is an example, not a claim that every workspace contains or uses HyperFrames.
