"""Per-project data directories (.gib/ inside each project)."""
from __future__ import annotations

from pathlib import Path

_GITIGNORE_ENTRY = ".gib/"
_LEGACY_GLOBAL_DB_NAMES = ("memory.db", "checkpoints.db")
_legacy_cleanup_done = False


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
    if not root.is_dir():
        return False

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
    """Remove deprecated global DB files from ~/.gib/ (once per process)."""
    global _legacy_cleanup_done
    if _legacy_cleanup_done:
        return []

    _legacy_cleanup_done = True
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
    data_dir = project_data_dir(project_root)
    ensure_gitignore(project_root)
    return data_dir


def sqlalchemy_sqlite_url(db_path: Path) -> str:
    """Build a SQLAlchemy SQLite URL from an absolute filesystem path."""
    return f"sqlite:///{db_path.resolve().as_posix()}"


def aiosqlite_conn_string(db_path: Path) -> str:
    """Connection string for LangGraph AsyncSqliteSaver / aiosqlite.connect()."""
    resolved = db_path.resolve()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    return str(resolved)


def is_legacy_global_db_path(path_str: str, db_name: str) -> bool:
    """True when path_str points at the deprecated global ~/.gib/<db_name>."""
    if path_str in (f".gib/{db_name}", f"~/.gib/{db_name}"):
        return True
    expanded = Path(path_str).expanduser()
    legacy = Path.home() / ".gib" / db_name
    try:
        return expanded.resolve() == legacy.resolve()
    except OSError:
        return expanded == legacy


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
