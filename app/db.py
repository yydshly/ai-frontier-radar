"""Database session and engine management."""
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import sessionmaker, declarative_base

from app.config import DATABASE_URL


def ensure_sqlite_parent_dir(database_url: str) -> None:
    """
    Ensure the parent directory of a SQLite database file exists.

    Uses SQLAlchemy's make_url for proper URL parsing.
    Handles:
    - sqlite:///./data/ai_frontier_radar.db -> creates data/
    - sqlite:////absolute/path/xxx.db -> creates parent dir
    - sqlite:///:memory: -> does nothing
    - Non-SQLite databases -> does nothing
    """
    url = make_url(database_url)

    if not url.drivername.startswith("sqlite"):
        return

    database = url.database

    if not database or database == ":memory:":
        return

    db_path = Path(database)
    parent = db_path.parent

    if parent and str(parent) != ".":
        parent.mkdir(parents=True, exist_ok=True)


# Ensure data directory exists before creating engine
ensure_sqlite_parent_dir(DATABASE_URL)

engine = create_engine(
    DATABASE_URL,
    connect_args=(
        {"check_same_thread": False, "timeout": 30}
        if "sqlite" in DATABASE_URL
        else {}
    ),
)


if engine.dialect.name == "sqlite":
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, _connection_record):
        """Enable WAL + a busy timeout so concurrent writers (fetch / background
        summarize+compile / report) don't immediately hit 'database is locked'.
        WAL allows readers concurrent with a writer; synchronous=NORMAL is the
        recommended durable pairing with WAL."""
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# ── Lightweight idempotent migrations ────────────────────────────────────────
# The project uses Base.metadata.create_all() (no Alembic). create_all() does
# NOT add indexes/columns to an already-existing table, so schema additions on
# an existing DB need an explicit step. This list of "CREATE INDEX IF NOT EXISTS"
# converges fresh and existing databases; index names match SQLAlchemy's
# index=True convention (ix_<table>_<column>) so they never duplicate.
_INDEX_MIGRATIONS: tuple[tuple[str, str, str], ...] = (
    ("ix_source_items_first_seen_at", "source_items", "first_seen_at"),
    ("ix_source_items_last_seen_at", "source_items", "last_seen_at"),
    ("ix_source_items_status", "source_items", "status"),
)


def apply_runtime_migrations(bind=None) -> list[str]:
    """Apply idempotent schema migrations (currently: indexes). Safe to run on
    every startup and repeatedly. Returns the index names ensured."""
    target = bind or engine
    ensured: list[str] = []
    with target.begin() as conn:
        for index_name, table, column in _INDEX_MIGRATIONS:
            conn.exec_driver_sql(
                f"CREATE INDEX IF NOT EXISTS {index_name} ON {table} ({column})"
            )
            ensured.append(index_name)
    return ensured


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables."""
    from app.models import (  # noqa: F401
        InsightCard,
        Source,
        SourceItem,
        FetchRun,
        CardDecision,
        InsightCardBilingualReport,
    )
    Base.metadata.create_all(bind=engine)
    # Converge existing databases (create_all won't add indexes to existing tables).
    apply_runtime_migrations()
