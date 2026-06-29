"""Per-project data directories (.gib/ inside each project)."""
from __future__ import annotations

import hashlib
import sqlite3
import tempfile
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


def ensure_project_data_layout(project_root: Path | str | None = None) -> Path | None:
    """Prepare per-project storage: .gib/, .gitignore entry, legacy cleanup.

    Never raises: storage resolution has its own fallbacks, so a read-only or
    otherwise unusable project directory must not crash GIB here.
    """
    try:
        cleanup_legacy_global_databases()
    except OSError:
        pass

    data_dir: Path | None = None
    try:
        data_dir = project_data_dir(project_root)
    except OSError:
        data_dir = None

    try:
        ensure_gitignore(project_root)
    except OSError:
        pass

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
    """Return <project>/.gib, attempting to create it (best-effort).

    Does not raise if the directory cannot be created (e.g. read-only project);
    storage resolution falls back to other writable locations in that case.
    """
    root = resolve_project_root(project_root)
    data_dir = root / ".gib"
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
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


def _project_id(project_root: Path | str | None = None) -> str:
    """Stable short identifier for a project, used for fallback storage dirs."""
    root = resolve_project_root(project_root)
    digest = hashlib.sha1(str(root).encode("utf-8")).hexdigest()[:12]
    return f"{root.name or 'root'}-{digest}"


def _can_open_sqlite(db_path: Path) -> bool:
    """Return True if a SQLite database can actually be opened at db_path."""
    try:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        if db_path.exists() and db_path.is_dir():
            return False
        conn = sqlite3.connect(str(db_path))
        try:
            conn.execute("PRAGMA user_version;")
        finally:
            conn.close()
        return True
    except (OSError, sqlite3.Error):
        return False


def _fallback_db_candidates(db_name: str, project_root: Path | str | None) -> list[Path]:
    """Ordered fallback locations for a database file, most-preferred first."""
    project_id = _project_id(project_root)
    candidates = [
        Path.home() / ".gib" / "projects" / project_id / db_name,
        Path(tempfile.gettempdir()) / "gib" / project_id / db_name,
    ]
    # De-duplicate while preserving order.
    seen: set[str] = set()
    unique: list[Path] = []
    for cand in candidates:
        key = str(cand)
        if key not in seen:
            seen.add(key)
            unique.append(cand)
    return unique


def find_writable_db_path(
    preferred: Path,
    db_name: str,
    project_root: Path | str | None = None,
) -> Path:
    """Return the first SQLite path that can actually be opened.

    Tries, in order: the preferred path, the per-project ``.gib`` path, a
    home-based fallback, then a temp-dir fallback. Guarantees a usable path so
    callers never surface "unable to open database file".
    """
    candidates: list[Path] = [preferred]
    try:
        candidates.append(project_data_dir(project_root) / db_name)
    except OSError:
        pass
    candidates.extend(_fallback_db_candidates(db_name, project_root))

    seen: set[str] = set()
    for cand in candidates:
        resolved = cand.expanduser()
        key = str(resolved)
        if key in seen:
            continue
        seen.add(key)
        if _can_open_sqlite(resolved):
            return resolved

    # Last resort: a unique temp file that is essentially always writable.
    tmp = Path(tempfile.mkdtemp(prefix="gib-")) / db_name
    return tmp
