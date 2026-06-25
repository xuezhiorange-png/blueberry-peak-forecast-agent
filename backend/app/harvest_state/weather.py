from __future__ import annotations

from decimal import Decimal

from backend.app.harvest_state.canonical import quantize_ratio
from backend.app.harvest_state.enums import BlockerCode, WeatherCombinationMethod
from backend.app.harvest_state.schemas import WeatherEfficiencyRuleConfig, WeatherFeatureBand


def _band_matches(band: WeatherFeatureBand, value: Decimal) -> bool:
    lower_ok = value >= band.lower_bound if band.lower_inclusive else value > band.lower_bound
    upper_ok = value <= band.upper_bound if band.upper_inclusive else value < band.upper_bound
    return lower_ok and upper_ok


def validate_weather_rule_config(config: WeatherEfficiencyRuleConfig) -> list[str]:
    blockers: list[str] = []
    seen_feature_ids: set[str] = set()
    for rule in config.feature_rules:
        if rule.feature_id in seen_feature_ids:
            blockers.append(f"{BlockerCode.DUPLICATE_WEATHER_FEATURE_RULE}:{rule.feature_id}")
            continue
        seen_feature_ids.add(rule.feature_id)
        bands = sorted(rule.bands, key=lambda item: (item.lower_bound, item.upper_bound))
        if len(bands) == 1 and bands[0].lower_bound == bands[0].upper_bound:
            blockers.append(f"{BlockerCode.WEATHER_RULE_BAND_GAP}:{rule.feature_id}")
            continue
        for band in bands:
            if band.lower_bound > band.upper_bound:
                blockers.append(f"{BlockerCode.WEATHER_RULE_INVALID_BOUNDS}:{rule.feature_id}")
                break
        for current, nxt in zip(bands, bands[1:], strict=False):
            overlaps = nxt.lower_bound < current.upper_bound or (
                nxt.lower_bound == current.upper_bound
                and current.upper_inclusive
                and nxt.lower_inclusive
            )
            if overlaps:
                blockers.append(f"{BlockerCode.WEATHER_RULE_BAND_OVERLAP}:{rule.feature_id}")
                break
            no_gap = nxt.lower_bound == current.upper_bound and (
                current.upper_inclusive or nxt.lower_inclusive
            )
            if nxt.lower_bound > current.upper_bound or not no_gap:
                blockers.append(f"{BlockerCode.WEATHER_RULE_BAND_GAP}:{rule.feature_id}")
                break
    return blockers


def compute_weather_efficiency_ratio(
    *,
    config: WeatherEfficiencyRuleConfig,
    feature_values: dict[str, Decimal],
) -> Decimal:
    if config.combination_method is not WeatherCombinationMethod.MULTIPLY:
        raise ValueError("unsupported weather combination method")

    ratio = Decimal("1")
    rules_by_feature = {rule.feature_id: rule for rule in config.feature_rules}
    for feature_id in config.required_feature_ids:
        if feature_id not in feature_values:
            raise ValueError(f"{BlockerCode.MISSING_WEATHER_FEATURE}:{feature_id}")
        rule = rules_by_feature[feature_id]
        matches = [band for band in rule.bands if _band_matches(band, feature_values[feature_id])]
        if len(matches) != 1:
            raise ValueError(f"{BlockerCode.WEATHER_RULE_BAND_GAP}:{feature_id}")
        ratio *= matches[0].multiplier
    clamped = min(config.maximum_ratio, max(config.minimum_ratio, ratio))
    return quantize_ratio(clamped)
