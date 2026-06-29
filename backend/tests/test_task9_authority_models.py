from __future__ import annotations

from sqlalchemy import Date, DateTime, Integer, Numeric, Text, Time
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from backend.app.models import (
    Task9AuthorityLifecycleEvent,
    Task9CapacityPoolDefinition,
    Task9CapacityPoolMember,
    Task9DailyCapacityAuthority,
    Task9HolidayCalendarDate,
    Task9HolidayCalendarVersion,
    Task9InitialInventoryCohort,
    Task9InitialInventorySnapshot,
    Task9MatureInventoryLossAuthority,
    Task9RunParameterPackage,
    Task9WeatherRuleConfigVersion,
)


def _column(table_name: str, name: str):
    table = {
        Task9CapacityPoolDefinition.__tablename__: Task9CapacityPoolDefinition.__table__,
        Task9CapacityPoolMember.__tablename__: Task9CapacityPoolMember.__table__,
        Task9DailyCapacityAuthority.__tablename__: Task9DailyCapacityAuthority.__table__,
        Task9RunParameterPackage.__tablename__: Task9RunParameterPackage.__table__,
        Task9HolidayCalendarVersion.__tablename__: Task9HolidayCalendarVersion.__table__,
        Task9HolidayCalendarDate.__tablename__: Task9HolidayCalendarDate.__table__,
        Task9WeatherRuleConfigVersion.__tablename__: Task9WeatherRuleConfigVersion.__table__,
        Task9InitialInventorySnapshot.__tablename__: Task9InitialInventorySnapshot.__table__,
        Task9InitialInventoryCohort.__tablename__: Task9InitialInventoryCohort.__table__,
        (
            Task9MatureInventoryLossAuthority.__tablename__
        ): Task9MatureInventoryLossAuthority.__table__,
        Task9AuthorityLifecycleEvent.__tablename__: Task9AuthorityLifecycleEvent.__table__,
    }[table_name]
    return table.c[name]


def test_task9_authority_model_tablenames_and_exports() -> None:
    assert Task9CapacityPoolDefinition.__tablename__ == "task9_capacity_pool_definition"
    assert Task9CapacityPoolMember.__tablename__ == "task9_capacity_pool_member"
    assert Task9DailyCapacityAuthority.__tablename__ == "task9_daily_capacity_authority"
    assert Task9RunParameterPackage.__tablename__ == "task9_run_parameter_package"
    assert Task9HolidayCalendarVersion.__tablename__ == "task9_holiday_calendar_version"
    assert Task9HolidayCalendarDate.__tablename__ == "task9_holiday_calendar_date"
    assert Task9WeatherRuleConfigVersion.__tablename__ == "task9_weather_rule_config_version"
    assert Task9InitialInventorySnapshot.__tablename__ == "task9_initial_inventory_snapshot"
    assert Task9InitialInventoryCohort.__tablename__ == "task9_initial_inventory_cohort"
    assert (
        Task9MatureInventoryLossAuthority.__tablename__ == "task9_mature_inventory_loss_authority"
    )
    assert Task9AuthorityLifecycleEvent.__tablename__ == "task9_authority_lifecycle_event"


def test_task9_authority_core_column_types_and_nullability() -> None:
    assert isinstance(_column("task9_capacity_pool_definition", "effective_from").type, Date)
    assert isinstance(_column("task9_capacity_pool_definition", "status_changed_at").type, DateTime)
    assert isinstance(
        _column("task9_daily_capacity_authority", "daily_capacity_revision").type, Integer
    )
    assert isinstance(
        _column("task9_daily_capacity_authority", "planned_picker_count").type, Numeric
    )
    assert isinstance(_column("task9_run_parameter_package", "farm_timezone").type, Text)
    assert isinstance(
        _column("task9_run_parameter_package", "harvest_bucket_anchor_local_time").type, Time
    )
    assert isinstance(
        _column("task9_authority_lifecycle_event", "authority_business_version").type, Text
    )
    assert isinstance(_column("task9_authority_lifecycle_event", "transitioned_at").type, DateTime)
    assert _column("task9_capacity_pool_member", "subfarm_id").nullable is True
    assert _column("task9_capacity_pool_member", "farm_id").nullable is False
    assert _column("task9_daily_capacity_authority", "consumable_to_local_date").nullable is True
    assert _column("task9_authority_lifecycle_event", "old_status").nullable is True
    assert _column("task9_authority_lifecycle_event", "new_status").nullable is False


def test_task9_authority_relationship_foreign_keys_present() -> None:
    member_fks = {fk.target_fullname for fk in Task9CapacityPoolMember.__table__.foreign_keys}
    assert "task9_capacity_pool_definition.id" in member_fks
    assert "dim_farm.id" in member_fks
    assert "dim_variety.id" in member_fks

    daily_fks = {fk.target_fullname for fk in Task9DailyCapacityAuthority.__table__.foreign_keys}
    assert "task9_capacity_pool_definition.id" in daily_fks
    assert "task9_daily_capacity_authority.id" in daily_fks

    run_package_fks = {fk.target_fullname for fk in Task9RunParameterPackage.__table__.foreign_keys}
    assert "task9_holiday_calendar_version.id" in run_package_fks
    assert "task9_weather_rule_config_version.id" in run_package_fks


def test_task9_authority_models_compile_without_p0_7b_only_constraints() -> None:
    tables = (
        Task9CapacityPoolDefinition.__table__,
        Task9CapacityPoolMember.__table__,
        Task9DailyCapacityAuthority.__table__,
        Task9RunParameterPackage.__table__,
        Task9HolidayCalendarVersion.__table__,
        Task9HolidayCalendarDate.__table__,
        Task9WeatherRuleConfigVersion.__table__,
        Task9InitialInventorySnapshot.__table__,
        Task9InitialInventoryCohort.__table__,
        Task9MatureInventoryLossAuthority.__table__,
        Task9AuthorityLifecycleEvent.__table__,
    )
    for table in tables:
        sql = str(CreateTable(table).compile(dialect=postgresql.dialect()))
        assert "EXCLUDE USING" not in sql
        assert "UNIQUE NULLS NOT DISTINCT" not in sql
        assert "GENERATED ALWAYS AS" not in sql


def test_member_table_has_no_plain_unique_constraint() -> None:
    """P1-1: Plain UniqueConstraint absent; NULLS NOT DISTINCT deferred to P0-7B."""
    uc_names = [
        c.name for c in Task9CapacityPoolMember.__table__.constraints
        if hasattr(c, "name") and c.name == "uq_task9_capacity_pool_member_business_key"
    ]
    assert uc_names == [], (
        "Plain UniqueConstraint must be removed; UNIQUE NULLS NOT DISTINCT goes to P0-7B"
    )
