"""Unit tests for postgres_test_support: pure validation logic.

These tests require NO database connection — they test the pure
validate_postgres_test_identity function only.
"""

from __future__ import annotations

import pytest

from backend.tests.postgres_test_support import validate_postgres_test_identity


class TestValidatePostgresTestIdentity:
    """Pure validation: no DB connection, no side effects."""

    def test_correct_test_configuration_accepted(self) -> None:
        """All three sources match blueberry_peak_test → accepted."""
        validate_postgres_test_identity(
            app_env="test",
            environment_database="blueberry_peak_test",
            configured_database="blueberry_peak_test",
            actual_database="blueberry_peak_test",
        )

    def test_app_env_local_rejected(self) -> None:
        with pytest.raises(ValueError, match="APP_ENV"):
            validate_postgres_test_identity(
                app_env="local",
                environment_database="blueberry_peak_test",
                configured_database="blueberry_peak_test",
                actual_database="blueberry_peak_test",
            )

    def test_app_env_none_rejected(self) -> None:
        with pytest.raises(ValueError, match="APP_ENV"):
            validate_postgres_test_identity(
                app_env=None,
                environment_database="blueberry_peak_test",
                configured_database="blueberry_peak_test",
                actual_database="blueberry_peak_test",
            )

    def test_environment_db_blueberry_peak_rejected(self) -> None:
        with pytest.raises(ValueError, match="protected database"):
            validate_postgres_test_identity(
                app_env="test",
                environment_database="blueberry_peak",
                configured_database="blueberry_peak",
                actual_database="blueberry_peak",
            )

    def test_configured_db_blueberry_peak_rejected(self) -> None:
        with pytest.raises(ValueError, match="mismatch"):
            validate_postgres_test_identity(
                app_env="test",
                environment_database="blueberry_peak_test",
                configured_database="blueberry_peak",
                actual_database="blueberry_peak_test",
            )

    def test_actual_db_blueberry_peak_rejected(self) -> None:
        with pytest.raises(ValueError, match="mismatch"):
            validate_postgres_test_identity(
                app_env="test",
                environment_database="blueberry_peak_test",
                configured_database="blueberry_peak_test",
                actual_database="blueberry_peak",
            )

    def test_actual_db_postgres_rejected(self) -> None:
        with pytest.raises(ValueError, match="mismatch"):
            validate_postgres_test_identity(
                app_env="test",
                environment_database="blueberry_peak_test",
                configured_database="blueberry_peak_test",
                actual_database="postgres",
            )

    def test_environment_configured_mismatch_rejected(self) -> None:
        with pytest.raises(ValueError, match="mismatch"):
            validate_postgres_test_identity(
                app_env="test",
                environment_database="blueberry_peak_test",
                configured_database="some_other_db",
                actual_database="blueberry_peak_test",
            )

    def test_configured_actual_mismatch_rejected(self) -> None:
        with pytest.raises(ValueError, match="mismatch"):
            validate_postgres_test_identity(
                app_env="test",
                environment_database="blueberry_peak_test",
                configured_database="blueberry_peak_test",
                actual_database="some_other_db",
            )

    def test_password_not_in_error_messages(self) -> None:
        """Ensure no password sentinel appears in any error message."""
        try:
            validate_postgres_test_identity(
                app_env="local",
                environment_database="blueberry_peak_test",
                configured_database="blueberry_peak_test",
                actual_database="blueberry_peak_test",
            )
        except ValueError as e:
            msg = str(e).lower()
            assert "password" not in msg, f"Error message contains 'password': {e}"
            assert "secret" not in msg, f"Error message contains 'secret': {e}"
            assert "dsn" not in msg, f"Error message contains 'dsn': {e}"
