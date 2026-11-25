"""Pure energy surplus and target SOC calculation engine."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime
import math

from .estimator import estimate_daytime_load
from .models import (
    BatteryConfig,
    CalculationResult,
    CalculationStatus,
    DaytimeLoadSample,
    EstimationMethod,
    LoadEstimationResult,
)


def _is_valid_non_negative(value: float | None) -> bool:
    """Return True if value is a finite non-negative number."""
    return (
        value is not None
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value >= 0.0
    )


def _invalid_result(
    *,
    status_code: CalculationStatus,
    reason: str,
    pv_forecast_kwh: float | None,
    current_soc_pct: float | None,
    load_estimation: LoadEstimationResult | None,
    calculated_at: datetime | None,
    target_night_date: date | None,
    config: BatteryConfig,
) -> CalculationResult:
    """Construct a fail-safe invalid calculation result."""
    return CalculationResult(
        is_valid=False,
        status_code=status_code,
        reason=reason,
        target_soc_pct=None,
        target_soc_raw=None,
        surplus_kwh=None,
        solar_soc_gain_pct=None,
        grid_energy_required_kwh=None,
        pv_forecast_kwh=pv_forecast_kwh,
        current_soc_pct=current_soc_pct,
        load_estimation=load_estimation,
        was_clamped=False,
        clamp_bound=None,
        calculated_at=calculated_at,
        target_night_date=target_night_date,
        config_snapshot=config,
    )


def calculate_target_soc(
    *,
    pv_forecast_kwh: float | None,
    load_samples: Sequence[DaytimeLoadSample],
    config: BatteryConfig,
    current_soc_pct: float | None = None,
    estimation_method: EstimationMethod = EstimationMethod.MEDIAN,
    lookback_days: int = 14,
    min_history_days: int = 3,
    reference_date: date | None = None,
    calculated_at: datetime | None = None,
    target_night_date: date | None = None,
) -> CalculationResult:
    """Calculate the minimum target SOC at the end of the economic window.

    Uses daytime house load history (during solar generation hours) rather than
    24-hour load so nighttime grid consumption does not understate daytime surplus.
    """
    config_errors = config.validate()
    if config_errors:
        return _invalid_result(
            status_code=CalculationStatus.INVALID_CONFIG,
            reason=" ".join(config_errors),
            pv_forecast_kwh=pv_forecast_kwh,
            current_soc_pct=current_soc_pct,
            load_estimation=None,
            calculated_at=calculated_at,
            target_night_date=target_night_date,
            config=config,
        )

    if not _is_valid_non_negative(pv_forecast_kwh):
        return _invalid_result(
            status_code=CalculationStatus.INVALID_PV_FORECAST,
            reason="pv_forecast_kwh must be a finite number >= 0.",
            pv_forecast_kwh=pv_forecast_kwh,
            current_soc_pct=current_soc_pct,
            load_estimation=None,
            calculated_at=calculated_at,
            target_night_date=target_night_date,
            config=config,
        )

    if current_soc_pct is not None and (
        isinstance(current_soc_pct, bool)
        or not math.isfinite(current_soc_pct)
        or current_soc_pct < 0.0
        or current_soc_pct > 100.0
    ):
        return _invalid_result(
            status_code=CalculationStatus.INVALID_CURRENT_SOC,
            reason="current_soc_pct must be in the range [0, 100] when provided.",
            pv_forecast_kwh=pv_forecast_kwh,
            current_soc_pct=current_soc_pct,
            load_estimation=None,
            calculated_at=calculated_at,
            target_night_date=target_night_date,
            config=config,
        )

    load_estimation = estimate_daytime_load(
        load_samples,
        method=estimation_method,
        lookback_days=lookback_days,
        min_history_days=min_history_days,
        reference_date=reference_date,
    )
    if not load_estimation.is_valid or load_estimation.estimated_kwh is None:
        return _invalid_result(
            status_code=load_estimation.status_code,
            reason=load_estimation.reason,
            pv_forecast_kwh=pv_forecast_kwh,
            current_soc_pct=current_soc_pct,
            load_estimation=load_estimation,
            calculated_at=calculated_at,
            target_night_date=target_night_date,
            config=config,
        )

    assert pv_forecast_kwh is not None
    surplus_kwh = max(0.0, float(pv_forecast_kwh) - load_estimation.estimated_kwh)
    solar_soc_gain_pct = (
        surplus_kwh * config.charge_efficiency / config.usable_battery_kwh
    ) * 100.0
    target_soc_raw = 100.0 - solar_soc_gain_pct + config.safety_margin_soc

    was_clamped = False
    clamp_bound: str | None = None
    clamped = target_soc_raw

    if target_soc_raw < config.min_operational_soc:
        clamped = config.min_operational_soc
        was_clamped = True
        clamp_bound = "min"
    elif target_soc_raw > config.max_operational_soc:
        clamped = config.max_operational_soc
        was_clamped = True
        clamp_bound = "max"

    target_soc_pct = int(round(clamped))
    min_int = math.ceil(config.min_operational_soc)
    max_int = math.floor(config.max_operational_soc)
    if min_int <= max_int:
        target_soc_pct = max(min_int, min(max_int, target_soc_pct))

    grid_energy_required_kwh: float | None = None
    if current_soc_pct is not None:
        delta_soc = max(0.0, float(target_soc_pct) - float(current_soc_pct))
        grid_energy_required_kwh = (
            (delta_soc / 100.0) * config.usable_battery_kwh
        ) / config.effective_grid_efficiency

    return CalculationResult(
        is_valid=True,
        status_code=CalculationStatus.OK,
        reason="Target SOC calculated successfully.",
        target_soc_pct=target_soc_pct,
        target_soc_raw=target_soc_raw,
        surplus_kwh=surplus_kwh,
        solar_soc_gain_pct=solar_soc_gain_pct,
        grid_energy_required_kwh=grid_energy_required_kwh,
        pv_forecast_kwh=float(pv_forecast_kwh),
        current_soc_pct=float(current_soc_pct) if current_soc_pct is not None else None,
        load_estimation=load_estimation,
        was_clamped=was_clamped,
        clamp_bound=clamp_bound,
        calculated_at=calculated_at,
        target_night_date=target_night_date,
        config_snapshot=config,
    )
