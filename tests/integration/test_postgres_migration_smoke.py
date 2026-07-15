from __future__ import annotations

"""
PostgreSQL migration smoke test (manual/CI gate).

STANDING RULE: Postgres-touching tests MUST use the dedicated test-only role
`complivibe_test_user` (LOGIN, CREATEDB, non-superuser, test/smoke DBs only) --
NEVER `complivibe_user` or any role live services authenticate with. Provision
once locally:

    sudo -u postgres psql -c "CREATE ROLE complivibe_test_user WITH LOGIN \
        PASSWORD 'complivibe_test_local_only' CREATEDB;"

Run manually before any production deploy:

POSTGRES_TEST_DATABASE_URL=postgresql+psycopg://complivibe_test_user:complivibe_test_local_only@localhost:5432/complivibe_pg_smoke_test \
PYTHONPATH=. .venv/bin/pytest \
tests/integration/test_postgres_migration_smoke.py \
-m postgres_smoke -v
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy.engine import URL, make_url

REPO_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"


def _admin_url_for(target: URL) -> URL:
    return target.set(database="postgres")


def _db_name(url: URL) -> str:
    return (url.database or "").strip()


def _assert_safe_test_db(url: URL) -> None:
    db_name = _db_name(url)
    if not db_name:
        raise AssertionError("POSTGRES_TEST_DATABASE_URL must include a database name")
    if db_name == "complivibe":
        raise AssertionError("Refusing to run smoke test against production database name 'complivibe'")
    if "smoke" not in db_name and "test" not in db_name:
        raise AssertionError(
            "POSTGRES_TEST_DATABASE_URL must point to a dedicated smoke/test database "
            f"(got '{db_name}')"
        )


def _drop_create_database(target_url: URL) -> None:
    admin_engine = sa.create_engine(_admin_url_for(target_url), isolation_level="AUTOCOMMIT")
    db_name = _db_name(target_url)
    with admin_engine.connect() as conn:
        conn.execute(
            sa.text(
                """
                SELECT pg_terminate_backend(pid)
                FROM pg_stat_activity
                WHERE datname = :db_name
                  AND pid <> pg_backend_pid()
                """
            ),
            {"db_name": db_name},
        )
        conn.execute(sa.text(f'DROP DATABASE IF EXISTS "{db_name}"'))
        conn.execute(sa.text(f'CREATE DATABASE "{db_name}"'))
    admin_engine.dispose()


def _drop_database(target_url: URL) -> None:
    admin_engine = sa.create_engine(_admin_url_for(target_url), isolation_level="AUTOCOMMIT")
    db_name = _db_name(target_url)
    with admin_engine.connect() as conn:
        conn.execute(
            sa.text(
                """
                SELECT pg_terminate_backend(pid)
                FROM pg_stat_activity
                WHERE datname = :db_name
                  AND pid <> pg_backend_pid()
                """
            ),
            {"db_name": db_name},
        )
        conn.execute(sa.text(f'DROP DATABASE IF EXISTS "{db_name}"'))
    admin_engine.dispose()


def _run_alembic(cmd: list[str], db_url: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["DATABASE_URL"] = db_url
    env["PYTHONPATH"] = "."
    return subprocess.run(
        [sys.executable, "-m", "alembic", *cmd],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.postgres_smoke
def test_postgres_migration_smoke_upgrade_head() -> None:
    db_url = os.getenv("POSTGRES_TEST_DATABASE_URL")
    if not db_url:
        pytest.skip("POSTGRES_TEST_DATABASE_URL is not set; skipping PostgreSQL smoke test")

    target_url = make_url(db_url)
    if not target_url.drivername.startswith("postgresql"):
        pytest.skip("POSTGRES_TEST_DATABASE_URL is not PostgreSQL; skipping")
    _assert_safe_test_db(target_url)

    _drop_create_database(target_url)
    try:
        upgraded = _run_alembic(["upgrade", "head"], db_url)
        assert upgraded.returncode == 0, (
            f"alembic upgrade head failed\nSTDOUT:\n{upgraded.stdout}\nSTDERR:\n{upgraded.stderr}"
        )

        current = _run_alembic(["current"], db_url)
        assert current.returncode == 0, (
            f"alembic current failed\nSTDOUT:\n{current.stdout}\nSTDERR:\n{current.stderr}"
        )

        cfg = Config(str(ALEMBIC_INI))
        cfg.set_main_option("script_location", "alembic")
        scripts = ScriptDirectory.from_config(cfg)
        expected_head = scripts.get_current_head()
        assert expected_head, "Could not resolve alembic head revision"
        assert expected_head in current.stdout, (
            f"Expected head {expected_head} not found in alembic current output:\n{current.stdout}"
        )

        engine = sa.create_engine(db_url)
        try:
            with engine.connect() as conn:
                inspector = sa.inspect(conn)
                tables = set(inspector.get_table_names())
                assert "obligations" in tables
                assert "memberships" in tables
                assert "subscription_plans" in tables
                assert "org_email_configs" in tables
                # Historical naming differed; accept either framework table name.
                assert ("compliance_frameworks" in tables) or ("frameworks" in tables)
        finally:
            engine.dispose()
    finally:
        _drop_database(target_url)

