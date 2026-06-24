from app.core.config import Settings


def test_settings_loads_from_env(monkeypatch):
    monkeypatch.setenv("APP_NAME", "CompliVibe")
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("API_V1_PREFIX", "/api/v1")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user:pass@localhost:5432/db")
    monkeypatch.setenv("SECRET_KEY", "test_secret_key_that_is_long_enough")
    monkeypatch.setenv("ACCESS_TOKEN_EXPIRE_MINUTES", "45")
    monkeypatch.setenv("BACKEND_CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")

    settings = Settings()

    assert settings.APP_NAME == "CompliVibe"
    assert settings.APP_ENV == "test"
    assert settings.API_V1_PREFIX == "/api/v1"
    assert settings.ACCESS_TOKEN_EXPIRE_MINUTES == 45
    assert len(settings.BACKEND_CORS_ORIGINS) == 2
