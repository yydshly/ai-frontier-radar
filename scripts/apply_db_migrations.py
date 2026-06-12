"""Apply lightweight idempotent DB migrations (indexes) to the configured DB.

The project uses Base.metadata.create_all() (no Alembic); create_all() does not
add indexes to already-existing tables. This CLI applies the same idempotent
"CREATE INDEX IF NOT EXISTS" migrations that run on app startup, so an existing
database can be converged without restarting the app.

Usage:
    python scripts/apply_db_migrations.py          # apply
    python scripts/apply_db_migrations.py --check   # report only, do not change
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import apply_runtime_migrations, engine  # noqa: E402


def _existing_indexes() -> set[str]:
    if engine.dialect.name != "sqlite":
        return set()
    with engine.begin() as conn:
        rows = conn.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ).fetchall()
    return {r[0] for r in rows}


def main() -> int:
    check_only = "--check" in sys.argv
    before = _existing_indexes()
    if check_only:
        from app.db import _INDEX_MIGRATIONS
        missing = [n for n, _, _ in _INDEX_MIGRATIONS if n not in before]
        print(f"DB: {engine.url}")
        print(f"existing indexes: {len(before)}")
        print(f"missing migration indexes: {missing or 'none'}")
        return 0
    ensured = apply_runtime_migrations()
    after = _existing_indexes()
    created = sorted(after - before)
    print(f"DB: {engine.url}")
    print(f"ensured indexes: {ensured}")
    print(f"newly created:   {created or 'none (already present)'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
