"""Selectable chill exposure calculators; no global blueberry model is selected."""

from __future__ import annotations

import math

from .schemas import ChillModel


class ChillAccumulator:
    def __init__(
        self, model: ChillModel, dynamic_constants: dict[str, float] | None = None
    ) -> None:
        self.model = model
        self.dynamic_constants = dynamic_constants
        if model is ChillModel.DYNAMIC_CHILL_PORTIONS and dynamic_constants is None:
            raise ValueError("Dynamic Model constants must be provenance-pinned literature priors")
        self.total = 0.0
        self._intermediate = 0.0
        self._previous_xi = 0.0

    def add_hour(self, temperature_c: float) -> float:
        if not math.isfinite(temperature_c):
            raise ValueError("Hourly temperature must be finite")
        if self.model is ChillModel.DYNAMIC_CHILL_PORTIONS and temperature_c <= -273.15:
            raise ValueError("Dynamic Model temperature must be above absolute zero")
        if self.model is ChillModel.CHILL_HOURS:
            increment = 1.0 if 0.0 <= temperature_c <= 7.2 else 0.0
        elif self.model is ChillModel.UTAH_CHILL_UNITS:
            increment = _utah_weight(temperature_c)
        else:
            increment = self._dynamic_portion_increment(temperature_c)
        self.total += increment
        return increment

    def _dynamic_portion_increment(self, temperature_c: float) -> float:
        """Fishman/Erez two-step Dynamic Model, classic published parameterization.

        This generic fruit-tree formulation is implemented as a selectable literature
        prior, not represented as blueberry-validated or a production default.
        """
        tk = temperature_c + 273.15
        if self.dynamic_constants is None:
            raise ValueError("Dynamic Model constants are unbound")
        e0 = self.dynamic_constants["dynamic_model_e0"]
        e1 = self.dynamic_constants["dynamic_model_e1"]
        a0 = self.dynamic_constants["dynamic_model_a0"]
        a1 = self.dynamic_constants["dynamic_model_a1"]
        slope = self.dynamic_constants["dynamic_model_slope"]
        tf = self.dynamic_constants["dynamic_model_tf_kelvin"]
        ftmprt = slope * tf * (tk - tf) / tk
        sr = math.exp(max(min(ftmprt, 700.0), -700.0))
        xi = sr / (1.0 + sr)
        xs = (a0 / a1) * math.exp(max(min((e1 - e0) / tk, 700.0), -700.0))
        ak1 = a1 * math.exp(max(min(-e1 / tk, 700.0), -700.0))
        previous = self._intermediate
        precursor = previous if previous < 1.0 else previous - previous * self._previous_xi
        current = xs - (xs - precursor) * math.exp(-ak1)
        self._intermediate = current
        self._previous_xi = xi
        return current * xi if current >= 1.0 else 0.0


def _utah_weight(temperature_c: float) -> float:
    if temperature_c < 1.4:
        return 0.0
    if temperature_c < 2.4:
        return 0.5
    if temperature_c <= 9.1:
        return 1.0
    if temperature_c <= 12.4:
        return 0.5
    if temperature_c <= 15.9:
        return 0.0
    if temperature_c <= 18.0:
        return -0.5
    return -1.0
