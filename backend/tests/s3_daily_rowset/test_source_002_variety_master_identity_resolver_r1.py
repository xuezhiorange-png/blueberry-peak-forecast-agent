"""SOURCE-002 variety master identity resolver R1 tests."""

from __future__ import annotations

import ast
import subprocess
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.app.models.master_data import Farm, Season, Subfarm, Variety
from backend.app.rolling_backtest.canonical import sha256_payload
from backend.app.s3_daily_rowset.pit_visible_incumbent_daily_curve_loader import (
    _resolve_business_grain,
)
from backend.app.s3_daily_rowset.source_002_variety_master_identity import (
    SOURCE_002_VARIETY_MASTER_IDENTITY_MAPPING_POLICY_VERSION,
    build_source_002_variety_master_identity_mapping_payload,
    canonical_master_variety_count,
    resolve_source_002_master_variety_identity,
    source_002_variety_master_identity_mapping_entries,
    source_002_variety_master_identity_mapping_sha256,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_APP_ROOT = _REPO_ROOT / "backend" / "app"
_RESOLVER_MODULE = _APP_ROOT / "s3_daily_rowset" / "source_002_variety_master_identity.py"
_PIT_LOADER_MODULE = _APP_ROOT / "s3_daily_rowset" / "pit_visible_incumbent_daily_curve_loader.py"

_GOVERNED_D_SERIES: tuple[tuple[str, str, str], ...] = (
    ("蓝莓原果D1", "D1", "D1"),
    ("蓝莓原果D2", "D2", "D2"),
    ("蓝莓原果D3", "D3", "D3"),
    ("蓝莓原果D5", "D5", "D5"),
    ("蓝莓原果D8", "D8", "D8"),
    ("蓝莓原果D10", "D10", "D10"),
    ("蓝莓原果D11", "D11", "D11"),
    ("蓝莓原果D12", "D12", "D12"),
    ("蓝莓原果D13", "D13", "D13"),
    ("蓝莓原果D19", "D19", "D19"),
    ("蓝莓原果D30", "D30", "D30"),
    ("蓝莓原果D31", "D31", "D31"),
)

_N_SERIES_TO_DX: tuple[str, ...] = (
    "蓝莓原果N109",
    "蓝莓原果N200",
    "蓝莓原果N70",
    "蓝莓原果N71",
    "蓝莓原果N72",
    "蓝莓原果N73",
    "蓝莓原果N76",
)

_UNKNOWN_SOURCE_KEYS: tuple[str, ...] = (
    "蓝莓原果N999",
    "UNKNOWN",
    "Dx",
    "d1",
    "蓝莓原果d1",
)


@pytest.fixture
async def master_data_session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    for table in (Season.__table__, Farm.__table__, Subfarm.__table__, Variety.__table__):
        async with engine.begin() as conn:
            await conn.run_sync(table.create)
    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_maker() as session:
        session.add(
            Season(
                id=1,
                code="2025~2026",
                start_date=date(2025, 8, 1),
                end_date=date(2026, 6, 30),
            )
        )
        session.add(Farm(id=1, name="测试农场"))
        session.add(Subfarm(id=1, farm_id=1, name="一分场"))
        master_codes = (
            "D1",
            "D2",
            "D3",
            "D5",
            "D8",
            "D10",
            "D11",
            "D12",
            "D13",
            "D19",
            "D30",
            "D31",
            "Dx",
        )
        variety_id = 100
        for code in master_codes:
            session.add(Variety(id=variety_id, code=code, name=code))
            variety_id += 1
        await session.commit()
        yield session
    await engine.dispose()


def test_full_governed_mapping_count() -> None:
    """FULL_GOVERNED_MAPPING_COUNT=20."""
    assert len(source_002_variety_master_identity_mapping_entries()) == 20


def test_canonical_master_variety_count() -> None:
    """CANONICAL_MASTER_VARIETY_COUNT=13."""
    assert canonical_master_variety_count() == 13


def test_mapping_policy_version() -> None:
    assert (
        SOURCE_002_VARIETY_MASTER_IDENTITY_MAPPING_POLICY_VERSION
        == "source-002-variety-master-identity-mapping-v1"
    )


def test_mapping_hash_replay() -> None:
    """MAPPING_HASH_REPLAY=PASS."""
    payload = build_source_002_variety_master_identity_mapping_payload()
    expected = sha256_payload(payload)
    assert source_002_variety_master_identity_mapping_sha256() == expected
    assert source_002_variety_master_identity_mapping_sha256() == expected


def test_n_series_to_dx() -> None:
    """N_SERIES_TO_DX=PASS."""
    for source_key in _N_SERIES_TO_DX:
        identity = resolve_source_002_master_variety_identity(source_key)
        assert identity is not None
        assert identity.code == "Dx"
        assert identity.name == "Dx"


def test_dx_exact_mapping() -> None:
    """DX_EXACT_MAPPING=PASS."""
    identity = resolve_source_002_master_variety_identity("蓝莓原果Dx")
    assert identity is not None
    assert identity.code == "Dx"
    assert identity.name == "Dx"


def test_d_series_exact_mapping() -> None:
    """D_SERIES_EXACT_MAPPING=PASS."""
    for source_key, code, name in _GOVERNED_D_SERIES:
        identity = resolve_source_002_master_variety_identity(source_key)
        assert identity is not None
        assert identity.code == code
        assert identity.name == name


def test_many_source_keys_one_master_identity() -> None:
    """MANY_SOURCE_KEYS_ONE_MASTER_IDENTITY=PASS."""
    dx_keys = ("蓝莓原果Dx",) + _N_SERIES_TO_DX
    identities = {resolve_source_002_master_variety_identity(key) for key in dx_keys}
    assert len(identities) == 1
    identity = identities.pop()
    assert identity is not None
    assert identity.code == "Dx"
    assert identity.name == "Dx"
    assert len(dx_keys) == 8


def test_unknown_mapping_fail_closed() -> None:
    """UNKNOWN_MAPPING_FAIL_CLOSED=PASS."""
    for source_key in _UNKNOWN_SOURCE_KEYS:
        assert resolve_source_002_master_variety_identity(source_key) is None


def test_resolver_does_not_invoke_normalization() -> None:
    """Resolver must not call historical or planning normalization helpers."""
    source = _RESOLVER_MODULE.read_text(encoding="utf-8")
    assert "normalize_variety" not in source
    assert "normalize_variety_lookup" not in source
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr in {"lower", "upper", "strip"}:
                pytest.fail("resolver must not perform case folding or trimming at runtime")
            if isinstance(func, ast.Name) and func.id in {"lower", "upper", "strip"}:
                pytest.fail("resolver must not perform case folding or trimming at runtime")


@pytest.mark.asyncio
async def test_pit_unknown_source_variety_fail_closed(master_data_session: AsyncSession) -> None:
    resolved = await _resolve_business_grain(
        master_data_session,
        season_business_key="2025~2026",
        farm_business_key="测试农场",
        subfarm_business_key="测试农场/一分场",
        variety_business_key="蓝莓原果N999",
    )
    assert resolved is None


@pytest.mark.asyncio
async def test_pit_master_code_name_drift_fail_closed(master_data_session: AsyncSession) -> None:
    """MASTER_CODE_NAME_DRIFT_FAIL_CLOSED=PASS."""
    await master_data_session.execute(delete(Variety).where(Variety.code == "Dx"))
    await master_data_session.commit()
    master_data_session.add(Variety(id=9001, code="Dx", name="WrongName"))
    master_data_session.add(Variety(id=9002, code="WrongCode", name="Dx"))
    await master_data_session.commit()

    assert (
        await _resolve_business_grain(
            master_data_session,
            season_business_key="2025~2026",
            farm_business_key="测试农场",
            subfarm_business_key="测试农场/一分场",
            variety_business_key="蓝莓原果N109",
        )
    ) is None
    assert (
        await _resolve_business_grain(
            master_data_session,
            season_business_key="2025~2026",
            farm_business_key="测试农场",
            subfarm_business_key="测试农场/一分场",
            variety_business_key="蓝莓原果Dx",
        )
    ) is None


@pytest.mark.asyncio
async def test_pit_exact_master_code_name_resolves(master_data_session: AsyncSession) -> None:
    resolved = await _resolve_business_grain(
        master_data_session,
        season_business_key="2025~2026",
        farm_business_key="测试农场",
        subfarm_business_key="测试农场/一分场",
        variety_business_key="蓝莓原果N109",
    )
    assert resolved is not None
    season_id, farm_id, subfarm_id, variety_id = resolved
    assert season_id == 1
    assert farm_id == 1
    assert subfarm_id == 1
    dx_variety = await master_data_session.get(Variety, variety_id)
    assert dx_variety is not None
    assert dx_variety.code == "Dx"
    assert dx_variety.name == "Dx"


@pytest.mark.asyncio
async def test_pit_d_series_resolves_to_own_master(master_data_session: AsyncSession) -> None:
    resolved = await _resolve_business_grain(
        master_data_session,
        season_business_key="2025~2026",
        farm_business_key="测试农场",
        subfarm_business_key="测试农场/一分场",
        variety_business_key="蓝莓原果D1",
    )
    assert resolved is not None
    _, _, _, variety_id = resolved
    variety = await master_data_session.get(Variety, variety_id)
    assert variety is not None
    assert variety.code == "D1"
    assert variety.name == "D1"


@pytest.mark.asyncio
async def test_pit_missing_master_row_fail_closed(master_data_session: AsyncSession) -> None:
    """Missing Dx master row should fail closed for N-series source keys."""
    await master_data_session.execute(delete(Variety).where(Variety.code == "Dx"))
    await master_data_session.commit()
    assert (
        await _resolve_business_grain(
            master_data_session,
            season_business_key="2025~2026",
            farm_business_key="测试农场",
            subfarm_business_key="测试农场/一分场",
            variety_business_key="蓝莓原果N70",
        )
    ) is None


def test_source_grain_identity_preserved_in_pit_index() -> None:
    """SOURCE_GRAIN_IDENTITY_PRESERVED=PASS."""
    loader_source = _PIT_LOADER_MODULE.read_text(encoding="utf-8")
    assert "lookup_key = (season, farm, subfarm, variety," in loader_source
    assert "grain_key = (season, farm, subfarm, variety)" in loader_source
    assert "variety_business_key=variety" in loader_source
    tree = ast.parse(loader_source)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id == "_append_daily_cells":
            keyword_names = [kw.arg for kw in node.keywords if kw.arg is not None]
            assert "variety" in keyword_names
            variety_kw = next(kw for kw in node.keywords if kw.arg == "variety")
            assert isinstance(variety_kw.value, ast.Name)
            assert variety_kw.value.id == "variety"


def test_pit_existing_authority_path_regression() -> None:
    """PIT_EXISTING_AUTHORITY_PATH_REGRESSION=PASS."""
    source = _PIT_LOADER_MODULE.read_text(encoding="utf-8")
    assert "resolve_source_002_master_variety_identity" in source
    assert "lookup_task10_prediction_run_id" in source
    assert "load_persisted_forecast_binding_authority" in source
    assert "Variety.code == variety_business_key" not in source


def test_pr550_regression() -> None:
    """PR550_REGRESSION=PASS."""
    result = subprocess.run(
        [
            "pytest",
            "backend/tests/forecast_quality/"
            "test_s3_b_persisted_task10_authority_reference_relation_r1.py",
            "-q",
        ],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_pr551_regression() -> None:
    """PR551_REGRESSION=PASS."""
    result = subprocess.run(
        [
            "pytest",
            "backend/tests/rolling_backtest/"
            "test_s3_b_persisted_task10_authority_production_writer_r1.py",
            "-q",
        ],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_pr552_regression() -> None:
    """PR552_REGRESSION=PASS."""
    result = subprocess.run(
        [
            "pytest",
            "backend/tests/forecast_quality/test_s3_b_live_pairing_authority_handoff_r1.py",
            "-q",
        ],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_pr553_regression() -> None:
    """PR553_REGRESSION=PASS."""
    result = subprocess.run(
        [
            "pytest",
            "backend/tests/s3_daily_rowset/"
            "test_accepted_s2_train_val_source_002_row_level_read_live_run_sync_correction_r1.py",
            "-k",
            "not materialization_entrypoint",
            "-q",
        ],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_pr554_regression() -> None:
    """PR554_REGRESSION=PASS."""
    result = subprocess.run(
        [
            "pytest",
            "backend/tests/forecast_quality/"
            "test_s3_b_single_loop_live_materialization_db_acquisition_r1.py",
            "-q",
        ],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
