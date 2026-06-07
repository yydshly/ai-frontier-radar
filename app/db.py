"""Database session and engine management."""
from pathlib import Path

from sqlalchemy import create_engine
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
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables."""
    from app.models import InsightCard, Source, SourceItem, FetchRun  # noqa: F401
    Base.metadata.create_all(bind=engine)
