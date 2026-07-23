import os
import shutil
import socket
import subprocess
import time
from collections.abc import Generator
from pathlib import Path

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

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEV_VAULT_BIN = _REPO_ROOT / ".dev_vault" / "bin" / "bao"
_DEV_VAULT_TOKEN = "test-dev-root-token"  # noqa: S105 - throwaway dev-mode token, in-memory server only
_DEV_VAULT_TRANSIT_KEY = "complivibe-secrets"


def _free_tcp_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def _wait_for_vault(addr: str, timeout_seconds: float = 30.0) -> bool:
    import hvac

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            client = hvac.Client(url=addr, token=_DEV_VAULT_TOKEN)
            if client.sys.is_initialized():
                return True
        except Exception:
            pass
        time.sleep(0.2)
    return False


def _start_dev_vault_once(binary: str) -> subprocess.Popen | None:
    port = _free_tcp_port()
    addr = f"http://127.0.0.1:{port}"
    process = subprocess.Popen(
        [
            binary,
            "server",
            "-dev",
            f"-dev-listen-address=127.0.0.1:{port}",
            f"-dev-root-token-id={_DEV_VAULT_TOKEN}",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if not _wait_for_vault(addr):
        process.terminate()
        process.wait(timeout=5)
        return None

    import hvac

    client = hvac.Client(url=addr, token=_DEV_VAULT_TOKEN)
    client.sys.enable_secrets_engine(backend_type="transit")
    client.secrets.transit.create_key(name=_DEV_VAULT_TRANSIT_KEY)

    os.environ["VAULT_ADDR"] = addr
    os.environ["VAULT_TOKEN"] = _DEV_VAULT_TOKEN
    os.environ["VAULT_TRANSIT_KEY_NAME"] = _DEV_VAULT_TRANSIT_KEY
    return process


def _start_dev_vault(attempts: int = 3) -> subprocess.Popen | None:
    """Starts a real, throwaway OpenBao dev-mode server for the test session so
    SecretsService.encrypt() (which only ever writes via vault) has a real
    backend to exercise. DEV/TEST ONLY -- never used in production, where
    VAULT_ADDR/VAULT_TOKEN point at an operator-managed OpenBao/Infisical
    deployment instead (see docs/runbooks/secrets_migration_fernet_to_vault.md).

    Retries a few times with a generous per-attempt timeout: under load, the
    binary occasionally isn't ready within one short window, which otherwise
    surfaces as a confusing wave of unrelated SecretsBackendError failures
    across every vault-dependent test in the session.
    """
    binary = str(_DEV_VAULT_BIN) if _DEV_VAULT_BIN.exists() else shutil.which("bao")
    if not binary:
        print("WARNING: no OpenBao binary found (.dev_vault/bin/bao or `bao` on PATH) -- "
              "vault-dependent tests will fail with SecretsBackendError. Run scripts/setup_dev_vault.sh first.")
        return None

    for attempt in range(1, attempts + 1):
        process = _start_dev_vault_once(binary)
        if process is not None:
            return process
        print(f"WARNING: dev OpenBao server failed to become ready (attempt {attempt}/{attempts})")

    print("WARNING: dev OpenBao server never became ready after retries -- "
          "vault-dependent tests will fail with SecretsBackendError.")
    return None


@pytest.fixture(scope="session", autouse=True)
def _dev_vault_session() -> Generator[None, None, None]:
    process = _start_dev_vault()
    try:
        yield
    finally:
        if process is not None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()


@pytest.fixture(scope="session", autouse=True)
def _base_env_session(_dev_vault_session: None) -> Generator[None, None, None]:
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


@pytest.fixture(autouse=True)
def _event_bus_listeners_registered() -> Generator[None, None, None]:
    """Restore the canonical EventBus listener set before every test.

    The EventBus is a process-global singleton and the app registers its
    listeners exactly once at startup (session-scoped `_test_app`). Several
    test modules clear the singleton in their own fixtures' teardown (to
    isolate custom listeners), which would otherwise leave the bus empty for
    any later test whose behavior depends on a registered listener -- e.g. the
    Phase-1-migrated vendor-staleness / DORA / geopolitical / OT-ICS cascades.
    Re-registering here before each test makes bus state order-independent.
    register_event_listeners() dedups, so this is idempotent.
    """
    from app.core.event_bus import EventBus
    from app.core.startup import register_event_listeners

    bus = EventBus.get_instance()
    bus.clear_listeners()
    register_event_listeners()
    yield


@pytest.fixture(autouse=True)
def _reset_rate_limit_cache() -> Generator[None, None, None]:
    """The rate-limiter's resolved-limit cache is a process-global singleton;
    clear it before each test so one test's cached org limit never leaks into
    another (tests truncate the DB between runs but reuse the singleton)."""
    from app.core.rate_limiter import rate_limiter

    rate_limiter.clear_limit_cache()
    yield
    rate_limiter.clear_limit_cache()


@pytest.fixture
def db_session(_test_engine, _test_session_factory, _base_metadata) -> Generator[Session, None, None]:
    db = _test_session_factory()
    try:
        yield db
    finally:
        db.rollback()
        db.close()
        _truncate_all_tables(_test_engine, _base_metadata)


@pytest.fixture
def seeded_reference_data(db_session):
    """Seed the global (non-org-scoped) framework catalogue and starter obligations.

    Production seeds this once at application startup (app/main.py lifespan). This
    harness truncates every table after each test, so a test that needs the catalogue
    present must ask for it explicitly.

    This exists because the framework/obligation GET handlers used to seed it lazily
    on read -- a read endpoint that wrote rows and committed. Those handlers are now
    side-effect-free, so the tests that depend on catalogue data request it here.

    It is deliberately NOT autouse: seeding globally would materialise frameworks like
    GDPR for every test, which collides with tests that create their own fixtures of
    the same code.
    """
    from app.services.seed_service import SeedService

    SeedService.ensure_starter_obligations(db_session)
    SeedService.ensure_framework_versions(db_session)
    db_session.commit()
    return db_session


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


@pytest.fixture(autouse=True)
def _default_org_entitlement(request, monkeypatch):
    """Access-model suite default: new orgs register onto enterprise/active.

    Mirrors the prod grandfather so the thousands of existing tests run
    fully-entitled and keep exercising their real subject, not the Stage 1c-4
    feature gate. This patches BillingService.start_free (the registration/
    onboarding landing) to seat the org on enterprise instead of Free.

    Opt out with @pytest.mark.free_registration when a test must observe the
    real Free-landing behaviour. Tests that want a specific tier should use
    bootstrap_org_user(plan=...), which sets the plan explicitly afterwards and
    therefore overrides this default regardless.
    """
    if request.node.get_closest_marker("free_registration"):
        yield
        return

    from app.models.organization import Organization
    from app.platform.services.billing_service import BillingService

    def _seat_enterprise(self, org_id):
        org = self.db.get(Organization, org_id)
        if org is not None:
            org.subscription_plan = "enterprise"
            org.subscription_status = "active"
            org.trial_ends_at = None
            self.db.flush()

    monkeypatch.setattr(BillingService, "start_free", _seat_enterprise)
    yield
