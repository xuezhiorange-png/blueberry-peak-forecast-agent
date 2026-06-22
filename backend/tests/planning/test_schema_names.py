from backend.app.models.planning import Base

TASK5_TABLES = {
    "dim_agro_climate_zone",
    "climate_zone_import_run",
    "location_reference",
    "parameter_library_version",
    "parameter_observation",
    "minimal_forecast_task",
    "parameter_inference_run",
    "parameter_inference_result",
}


def test_task5_constraint_and_index_names_fit_postgresql_identifier_limit() -> None:
    too_long: list[tuple[str, str, int]] = []

    for table in Base.metadata.tables.values():
        if table.name not in TASK5_TABLES:
            continue

        for constraint in table.constraints:
            if constraint.name and len(constraint.name) > 63:
                too_long.append((table.name, constraint.name, len(constraint.name)))

        for index in table.indexes:
            if index.name and len(index.name) > 63:
                too_long.append((table.name, index.name, len(index.name)))

    assert too_long == []
