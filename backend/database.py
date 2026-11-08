"""SQLAlchemy 数据库配置、用户与异步分析记录。"""

from datetime import datetime, timezone
import os
from pathlib import Path

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE_PATH = ROOT / "data" / "inventory.db"
DATABASE_URL = os.getenv(
    "DATABASE_URL", f"sqlite:///{DEFAULT_DATABASE_PATH.as_posix()}"
)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class AnalysisRecord(Base):
    __tablename__ = "analysis_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    task_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, unique=True, index=True
    )
    run_id: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    filename: Mapped[str] = mapped_column(String(255))
    digest: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(20), index=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    yolo_detection_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sam_mask_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    vlm_item_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


connect_args = (
    {"check_same_thread": False, "timeout": 30}
    if DATABASE_URL.startswith("sqlite")
    else {}
)
engine = create_engine(DATABASE_URL, connect_args=connect_args)


if DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def configure_sqlite(connection, _):
        cursor = connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def _upgrade_legacy_sqlite_database() -> None:
    """为早期 SQLite 数据库补列，不删除已有分析记录。"""
    if not DATABASE_URL.startswith("sqlite"):
        return
    with engine.begin() as connection:
        tables = {
            row[0]
            for row in connection.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        if "analysis_records" not in tables:
            return
        columns = {
            row[1]
            for row in connection.exec_driver_sql(
                "PRAGMA table_info(analysis_records)"
            )
        }
        additions = {
            "owner_id": "INTEGER",
            "task_id": "VARCHAR(64)",
            "started_at": "DATETIME",
        }
        for name, sql_type in additions.items():
            if name not in columns:
                connection.exec_driver_sql(
                    f"ALTER TABLE analysis_records ADD COLUMN {name} {sql_type}"
                )
        connection.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_analysis_records_owner_id "
            "ON analysis_records (owner_id)"
        )
        connection.exec_driver_sql(
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_analysis_records_task_id "
            "ON analysis_records (task_id)"
        )


def initialize_database() -> None:
    DEFAULT_DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    _upgrade_legacy_sqlite_database()
