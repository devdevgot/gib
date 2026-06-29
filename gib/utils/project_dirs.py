"""Per-project data directories (.gib/ inside each project)."""
from __future__ import annotations

from pathlib import Path

_GITIGNORE_ENTRY = ".gib/"
_LEGACY_GLOBAL_DB_NAMES = ("memory.db", "checkpoints.db")


def resolve_project_root(project_root: Path | str | None = None) -> Path:
    """Resolve project root, defaulting to the current working directory."""
    if project_root:
        return Path(project_root).expanduser().resolve()
    return Path.cwd().resolve()


def _gitignore_has_gib_entry(content: str) -> bool:
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        normalized = line.rstrip("/")
        if normalized in (".gib", "**/.gib") or line.endswith(".gib/"):
            return True
    return False


def ensure_gitignore(project_root: Path | str | None = None) -> bool:
    """Add .gib/ to the project .gitignore if it is missing."""
    root = resolve_project_root(project_root)
    gitignore = root / ".gitignore"

    if gitignore.exists():
        content = gitignore.read_text(encoding="utf-8")
        if _gitignore_has_gib_entry(content):
            return False
        suffix = "" if content.endswith("\n") or not content else "\n"
        gitignore.write_text(
            f"{content}{suffix}\n# GIB local data (memory, checkpoints, logs)\n{_GITIGNORE_ENTRY}\n",
            encoding="utf-8",
        )
        return True

    gitignore.write_text(
        f"# GIB local data (memory, checkpoints, logs)\n{_GITIGNORE_ENTRY}\n",
        encoding="utf-8",
    )
    return True


def cleanup_legacy_global_databases() -> list[Path]:
    """Remove deprecated global DB files from ~/.gib/."""
    gib_dir = Path.home() / ".gib"
    removed: list[Path] = []

    for name in _LEGACY_GLOBAL_DB_NAMES:
        for suffix in ("", "-wal", "-shm", "-journal"):
            path = gib_dir / f"{name}{suffix}"
            if path.is_file():
                path.unlink()
                removed.append(path)

    return removed


def ensure_project_data_layout(project_root: Path | str | None = None) -> Path:
    """Prepare per-project storage: .gib/, .gitignore entry, legacy cleanup."""
    cleanup_legacy_global_databases()
    ensure_gitignore(project_root)
    return project_data_dir(project_root)


def project_data_dir(project_root: Path | str | None = None) -> Path:
    """Return <project>/.gib, creating the directory if needed."""
    root = resolve_project_root(project_root)
    data_dir = root / ".gib"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def memory_db_path(project_root: Path | str | None = None) -> Path:
    """SQLite path for project memory (tasks, chat, paused runs)."""
    return project_data_dir(project_root) / "memory.db"


def checkpoint_db_path(project_root: Path | str | None = None) -> Path:
    """SQLite path for LangGraph checkpoints (gib resume)."""
    return project_data_dir(project_root) / "checkpoints.db"


def log_dir_path(project_root: Path | str | None = None) -> Path:
    """Log directory for a project."""
    log_dir = project_data_dir(project_root) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir
