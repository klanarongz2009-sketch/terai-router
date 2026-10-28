"""Workspace sandbox for Tagentic1: every file tool works inside one root folder.

A path is resolved against the root (symlinks followed) and refused when the real path is outside the root, so
``../x``, an absolute path elsewhere and a symlink that points out of the workspace are all blocked.
"""
from __future__ import annotations

import os
from pathlib import Path


class SandboxError(ValueError):
    """A path points outside the workspace."""


class Workspace:
    def __init__(self, root: str | os.PathLike | None = None) -> None:
        self.root = Path(root or os.getcwd()).expanduser().resolve()
        if not self.root.is_dir():
            raise SandboxError(f'workspace is not a folder: {self.root}')

    def resolve(self, path: str | os.PathLike | None) -> Path:
        """Real path of ``path`` inside the workspace, or SandboxError."""
        p = Path(str(path or '.')).expanduser()
        if not p.is_absolute():
            p = self.root / p
        real = Path(os.path.realpath(p))
        if real != self.root and self.root not in real.parents:
            raise SandboxError(f'path is outside the workspace ({self.root}): {path}')
        return real

    def rel(self, p: Path) -> str:
        r = str(Path(p).relative_to(self.root))
        return r if r else '.'
