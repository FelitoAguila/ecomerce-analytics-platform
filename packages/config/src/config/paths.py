from functools import lru_cache
from pathlib import Path

_WORKSPACE_MARKER = "[tool.uv.workspace]"


@lru_cache
def workspace_root(start: Path | None = None) -> Path:
    """Locate the uv workspace root: the nearest ancestor pyproject.toml declaring
    a [tool.uv.workspace] table. Falls back to the current working directory."""
    base = (start or Path.cwd()).resolve()
    for parent in [base, *base.parents]:
        pyproject = parent / "pyproject.toml"
        if pyproject.is_file() and _WORKSPACE_MARKER in pyproject.read_text(
            encoding="utf-8"
        ):
            return parent
    return base
