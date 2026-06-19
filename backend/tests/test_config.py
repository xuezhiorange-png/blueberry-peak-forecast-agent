from backend.app.core.config import AppSettings


def test_settings_load_from_environment(monkeypatch):
    monkeypatch.setenv("APP_NAME", "Test Blueberry Agent")
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("POSTGRES_HOST", "db.example.test")
    monkeypatch.setenv("POSTGRES_PORT", "15432")
    monkeypatch.setenv("POSTGRES_DB", "blueberry_test")
    monkeypatch.setenv("POSTGRES_USER", "agent")
    monkeypatch.setenv("POSTGRES_PASSWORD", "secret")
    monkeypatch.setenv("DB_POOL_SIZE", "7")
    monkeypatch.setenv("DB_MAX_OVERFLOW", "3")

    settings = AppSettings()

    assert settings.app_name == "Test Blueberry Agent"
    assert settings.app_env == "test"
    assert settings.log_level == "DEBUG"
    assert settings.postgres_host == "db.example.test"
    assert settings.postgres_port == 15432
    assert settings.postgres_db == "blueberry_test"
    assert settings.postgres_user == "agent"
    assert settings.postgres_password.get_secret_value() == "secret"
    assert settings.db_pool_size == 7
    assert settings.db_max_overflow == 3
    assert (
        settings.async_database_url
        == "postgresql+asyncpg://agent:secret@db.example.test:15432/blueberry_test"
    )
