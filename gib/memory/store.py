"""Long-term memory store using SQLite + SQLAlchemy."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    String,
    Text,
    create_engine,
    desc,
    func,
    select,
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from gib.config import get_config
from gib.utils import get_logger

logger = get_logger("gib.memory")


def normalize_project_path(project_path: str) -> str:
    """Canonical absolute path for consistent DB lookups."""
    if not project_path:
        return ""
    return str(Path(project_path).expanduser().resolve())


class Base(DeclarativeBase):
    pass


class TaskRecord(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    task_type = Column(String(64), nullable=False)
    prompt = Column(Text, nullable=False)
    model_used = Column(String(128), nullable=True)
    result_summary = Column(Text, nullable=True)
    cost_usd = Column(String(32), nullable=True)
    project_path = Column(String(512), nullable=True)
    status = Column(String(32), default="completed")  # completed | failed | cancelled


class SessionRecord(Base):
    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    project_path = Column(String(512), nullable=True)
    messages_json = Column(Text, default="[]")  # JSON array of chat messages
    metadata_json = Column(Text, default="{}")  # arbitrary session metadata


class ProjectProfile(Base):
    __tablename__ = "project_profiles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    project_path = Column(String(512), unique=True, nullable=False)
    profile_json = Column(Text, default="{}")  # language, framework, stack, etc.


class MemoryStore:
    """Manages all persistent memory for GIB."""

    def __init__(self, db_path: Path | None = None) -> None:
        path = db_path or get_config().memory_db_path()
        self._engine = create_engine(f"sqlite:///{path}", echo=False)
        Base.metadata.create_all(self._engine)
        self._session_factory = sessionmaker(bind=self._engine)

    # ── Task history ──────────────────────────────────────────────────────────

    def save_task(
        self,
        task_type: str,
        prompt: str,
        model_used: str = "",
        result_summary: str = "",
        cost_usd: float = 0.0,
        project_path: str = "",
        status: str = "completed",
    ) -> TaskRecord:
        with Session(self._engine) as session:
            record = TaskRecord(
                task_type=task_type,
                prompt=prompt[:8000],
                model_used=model_used,
                result_summary=result_summary[:50_000],
                cost_usd=str(cost_usd),
                project_path=normalize_project_path(project_path) or project_path,
                status=status,
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            self._enforce_max_history(session)
            return record

    def _enforce_max_history(self, session: Session) -> None:
        """Удаляет старые записи сверх memory.max_history."""
        max_history = get_config().memory.max_history
        count = session.scalar(select(func.count()).select_from(TaskRecord)) or 0
        if count <= max_history:
            return
        excess = count - max_history
        stmt = select(TaskRecord).order_by(TaskRecord.created_at.asc()).limit(excess)
        for record in session.scalars(stmt):
            session.delete(record)
        session.commit()

    def get_last_review(self, project_path: str = "") -> TaskRecord | None:
        """Возвращает последний review/doctor для проекта."""
        norm = normalize_project_path(project_path)
        with Session(self._engine) as session:
            for path in filter(None, [norm, project_path]):
                stmt = (
                    select(TaskRecord)
                    .where(TaskRecord.task_type.in_(["review", "doctor"]))
                    .where(TaskRecord.project_path == path)
                    .order_by(desc(TaskRecord.created_at))
                    .limit(1)
                )
                record = session.scalar(stmt)
                if record:
                    return record
            return None

    def recent_tasks(self, limit: int = 20, project_path: str = "") -> list[TaskRecord]:
        norm = normalize_project_path(project_path)
        with Session(self._engine) as session:
            if norm:
                stmt = (
                    select(TaskRecord)
                    .where(TaskRecord.project_path == norm)
                    .order_by(desc(TaskRecord.created_at))
                    .limit(limit)
                )
                tasks = list(session.scalars(stmt))
                if tasks:
                    return tasks
                if project_path and project_path != norm:
                    stmt = (
                        select(TaskRecord)
                        .where(TaskRecord.project_path == project_path)
                        .order_by(desc(TaskRecord.created_at))
                        .limit(limit)
                    )
                    return list(session.scalars(stmt))
            stmt = select(TaskRecord).order_by(desc(TaskRecord.created_at)).limit(limit)
            return list(session.scalars(stmt))

    # ── Sessions ──────────────────────────────────────────────────────────────

    def create_session(self, project_path: str = "") -> SessionRecord:
        norm = normalize_project_path(project_path) or project_path
        with Session(self._engine) as session:
            record = SessionRecord(project_path=norm)
            session.add(record)
            session.commit()
            session.refresh(record)
            return record

    def get_latest_session(self, project_path: str = "") -> SessionRecord | None:
        """Return the most recent chat session for a project."""
        norm = normalize_project_path(project_path)
        with Session(self._engine) as session:
            for path in filter(None, [norm, project_path]):
                stmt = (
                    select(SessionRecord)
                    .where(SessionRecord.project_path == path)
                    .order_by(desc(SessionRecord.created_at))
                    .limit(1)
                )
                record = session.scalar(stmt)
                if record:
                    return record
            return None

    def append_session_message(self, session_id: int, role: str, content: str) -> None:
        with Session(self._engine) as db_session:
            record = db_session.get(SessionRecord, session_id)
            if record:
                messages = json.loads(record.messages_json or "[]")
                messages.append({"role": role, "content": content})
                record.messages_json = json.dumps(messages)
                db_session.commit()

    def get_session_messages(self, session_id: int) -> list[dict[str, str]]:
        with Session(self._engine) as session:
            record = session.get(SessionRecord, session_id)
            if record:
                return json.loads(record.messages_json or "[]")
            return []

    def get_recent_chat_summary(self, project_path: str = "", limit_messages: int = 12) -> str:
        """Summarize recent chat turns for workflow context."""
        record = self.get_latest_session(project_path)
        if not record:
            return ""
        messages = self.get_session_messages(record.id)
        if not messages:
            return ""

        recent = messages[-limit_messages:]
        lines = ["## Recent Chat History"]
        for msg in recent:
            role = msg.get("role", "user")
            content = (msg.get("content") or "").strip()
            if not content or role == "system":
                continue
            label = "User" if role == "user" else "Assistant"
            lines.append(f"\n**{label}:** {content[:2000]}")
        return "\n".join(lines) if len(lines) > 1 else ""

    # ── Project profile ───────────────────────────────────────────────────────

    def save_project_profile(self, project_path: str, profile: dict[str, Any]) -> None:
        norm = normalize_project_path(project_path) or project_path
        with Session(self._engine) as session:
            existing = session.scalar(
                select(ProjectProfile).where(ProjectProfile.project_path == norm)
            )
            if existing:
                existing.profile_json = json.dumps(profile)
                existing.updated_at = datetime.utcnow()
            else:
                session.add(
                    ProjectProfile(
                        project_path=norm,
                        profile_json=json.dumps(profile),
                    )
                )
            session.commit()

    def get_project_profile(self, project_path: str) -> dict[str, Any]:
        norm = normalize_project_path(project_path)
        with Session(self._engine) as session:
            for path in filter(None, [norm, project_path]):
                record = session.scalar(
                    select(ProjectProfile).where(ProjectProfile.project_path == path)
                )
                if record:
                    return json.loads(record.profile_json or "{}")
            return {}
