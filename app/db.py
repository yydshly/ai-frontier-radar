"""Database session and engine management."""
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from app.config import DATABASE_URL


def ensure_sqlite_parent_dir(database_url: str) -> None:
    """
    Ensure the parent directory of a SQLite database file exists.

    Handles:
    - sqlite:///./data/ai_frontier_radar.db -> creates data/
    - sqlite:////absolute/path/xxx.db -> creates parent dir
    - sqlite:///:memory: -> does nothing
    - Non-SQLite databases -> does nothing
    """
    if not database_url.startswith("sqlite:"):
        return

    # Parse the URL to get the database file path
    parsed = urlparse(database_url)

    # :memory: has no file path
    if parsed.path == ":memory:" or not parsed.path:
        return

    # Get the directory part
    db_path = parsed.path
    # On Windows, urlparse may treat "D:/path" differently
    # Normalize: remove leading slash for relative paths like /./data/xxx
    if db_path.startswith("/./"):
        db_path = db_path[2:]  # remove leading /.
    elif db_path.startswith("/"):
        # Absolute path on Unix or Windows drive letter
        pass

    db_file = Path(db_path)

    # Determine parent directory
    if db_file.is_absolute():
        parent = db_file.parent
    else:
        # Relative path like ./data/ai_frontier_radar.db
        parent = db_file.parent

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
    from app.models import InsightCard  # noqa: F401
    Base.metadata.create_all(bind=engine)
