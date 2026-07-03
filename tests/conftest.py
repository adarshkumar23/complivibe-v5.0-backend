import os
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

_BASE_ENV = {
    "APP_NAME": "CompliVibe Backend Test",
    "APP_ENV": "test",
    "API_V1_PREFIX": "/api/v1",
    "DATABASE_URL": "sqlite+pysqlite:///./test.db",
    "SECRET_KEY": "test_secret_key_that_is_long_enough",
    "ACCESS_TOKEN_EXPIRE_MINUTES": "30",
    "BACKEND_CORS_ORIGINS": "http://localhost:3000",
}


@pytest.fixture(scope="session", autouse=True)
def _base_env_session() -> Generator[None, None, None]:
    # Session-scoped fixtures (e.g. _test_app) are set up before function-scoped
    # ones regardless of autouse, so the base env must be seeded here -- setting
    # it only in a function-scoped fixture would leave get_settings() reading a
    # bare/undefined environment the first time the session-scoped app is built.
    os.environ.update(_BASE_ENV)

    from app.core.config import get_settings

    get_settings.cache_clear()

    # bcrypt's default work factor (12 rounds, ~250-300ms/hash) is deliberately
    # slow for production password storage. The suite calls register/login
    # (i.e. hashes/verifies a password) well over a thousand times across
    # bootstrap_org_user() and friends, so at the default cost that's minutes
    # of pure CPU spent hashing test fixtures. Use the minimum valid bcrypt
    # cost for the test process only -- production code (app.core.security)
    # is untouched, this only swaps the CryptContext used during tests.
    import app.core.security as security_module
    from passlib.context import CryptContext

    security_module.pwd_context = CryptContext(
        schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=4
    )

    yield


@pytest.fixture(autouse=True)
def base_env(_base_env_session: None) -> Generator[None, None, None]:
    for key, value in _BASE_ENV.items():
        os.environ[key] = value

    from app.core.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(scope="session")
def _base_metadata():
    from app import models  # noqa: F401
    from app.db.base import Base

    return Base.metadata


@pytest.fixture(scope="session")
def _test_engine(_base_metadata):
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    _base_metadata.create_all(bind=engine)
    try:
        yield engine
    finally:
        _base_metadata.drop_all(bind=engine)


@pytest.fixture(scope="session")
def _test_session_factory(_test_engine):
    return sessionmaker(bind=_test_engine, autocommit=False, autoflush=False, class_=Session)


def _truncate_all_tables(engine, metadata) -> None:
    with engine.begin() as conn:
        conn.exec_driver_sql("PRAGMA foreign_keys=OFF")
        for table in reversed(metadata.sorted_tables):
            conn.execute(table.delete())
        try:
            # Reset AUTOINCREMENT counters when present.
            conn.exec_driver_sql("DELETE FROM sqlite_sequence")
        except OperationalError:
            # sqlite_sequence may not exist if no AUTOINCREMENT tables were created.
            pass
        finally:
            conn.exec_driver_sql("PRAGMA foreign_keys=ON")


@pytest.fixture
def db_session(_test_engine, _test_session_factory, _base_metadata) -> Generator[Session, None, None]:
    db = _test_session_factory()
    try:
        yield db
    finally:
        db.rollback()
        db.close()
        _truncate_all_tables(_test_engine, _base_metadata)


@pytest.fixture(scope="session")
def _test_app():
    from app.main import create_application

    return create_application()


@pytest.fixture(scope="session")
def _test_client(_test_app) -> Generator[TestClient, None, None]:
    # FastAPI lazily builds and caches each route's dependency-injection graph
    # on first match. Building a fresh app (and TestClient) per test throws
    # that cache away every time, forcing thousands of dependant-graph
    # rebuilds per test. Building the app/client once per session and only
    # swapping the `get_db` override per test keeps the cache warm while
    # still giving every test an isolated database session.
    with TestClient(_test_app) as test_client:
        yield test_client


@pytest.fixture
def client(_test_app, _test_client: TestClient, db_session: Session) -> Generator[TestClient, None, None]:
    from app.core.deps import get_db

    def override_get_db() -> Generator[Session, None, None]:
        yield db_session

    _test_app.dependency_overrides[get_db] = override_get_db
    try:
        yield _test_client
    finally:
        _test_app.dependency_overrides.pop(get_db, None)
