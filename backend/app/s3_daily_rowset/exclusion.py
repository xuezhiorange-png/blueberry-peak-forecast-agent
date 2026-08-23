"""Cell-level and day-level exclusion rules for S3-A."""

from __future__ import annotations

from backend.app.s3_daily_rowset.schemas import EvaluationInstanceCell

FORBIDDEN_VARIETIES = frozenset({"普鲜", "普青", "普冻", "废果"})
BASON_FACTORY_MARKERS = frozenset({"巴松", "巴松加工厂"})


def is_forbidden_variety(variety: str) -> bool:
    return variety in FORBIDDEN_VARIETIES


def is_bason_factory(farm: str) -> bool:
    return any(marker in farm for marker in BASON_FACTORY_MARKERS)


def is_cell_level_excluded(cell: EvaluationInstanceCell) -> bool:
    return is_forbidden_variety(cell.variety) or is_bason_factory(cell.farm)
