"""Tests for legacy config path migration."""
import gib.config.loader as loader
from gib.config import get_config
from gib.utils.project_dirs import is_legacy_global_db_path


def test_is_legacy_global_db_path_detects_tilde_and_absolute(tmp_path, monkeypatch):
    monkeypatch.setattr("gib.utils.project_dirs.Path.home", lambda: tmp_path)
    home_db = tmp_path / ".gib" / "memory.db"

    assert is_legacy_global_db_path("~/.gib/memory.db", "memory.db")
    assert is_legacy_global_db_path(".gib/memory.db", "memory.db")
    assert is_legacy_global_db_path(str(home_db), "memory.db")
    assert not is_legacy_global_db_path("/tmp/other/memory.db", "memory.db")


def test_migrate_global_config_paths(tmp_path, monkeypatch):
    monkeypatch.setattr("gib.config.loader.Path.home", lambda: tmp_path)
    gib_dir = tmp_path / ".gib"
    gib_dir.mkdir()
    cfg = gib_dir / "config.yaml"
    cfg.write_text(
        "memory:\n"
        "  db_path: ~/.gib/memory.db\n"
        "  checkpoint_db_path: ~/.gib/checkpoints.db\n"
        "logging:\n"
        "  log_dir: ~/.gib/logs\n",
        encoding="utf-8",
    )

    loader.get_config.cache_clear()
    loader._ensure_global_config()

    text = cfg.read_text(encoding="utf-8")
    assert "~/.gib/memory.db" not in text
    assert "~/.gib/checkpoints.db" not in text
    assert '.gib/memory.db' in text
    assert '.gib/checkpoints.db' in text

    loader.get_config.cache_clear()
    config = get_config()
    assert config.memory.db_path == ".gib/memory.db"
    assert config.memory.checkpoint_db_path == ".gib/checkpoints.db"
