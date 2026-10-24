"""Synthetic frozen coefficients are test fixtures, never a real M1 substitute."""

from datetime import date

from backend.research.v019_origin_models import compile_pair, fit_pair
from backend.tests.area_yield.test_v0_19_origin_models import fixture


def frozen_document():
    from backend.research.v019_real_training_cli import seal

    _, records, labels = fixture()
    fit = fit_pair(
        records, labels, allowed_seasons=("2023-2024",), evaluation_start=date(2024, 7, 1)
    )
    return seal({"experiments": {"B": fit}, "code_identity": "a" * 64})


def frozen_pair():
    return compile_pair(frozen_document()["payload"]["experiments"]["B"])
