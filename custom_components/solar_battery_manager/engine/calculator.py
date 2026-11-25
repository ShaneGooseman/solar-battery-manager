"""Pure energy surplus and target SOC calculation engine."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime, time, timedelta
import math
from zoneinfo import ZoneInfo

from .estimator import estimate_daytime_load
from .models import (
    BatteryConfig,
    CalculationResult,
    CalculationStatus,
    ChargeSchedulePlan,
    DaytimeLoadSample,
    EstimationMethod,
    LoadEstimationResult,
    ScheduleState,
    TariffScheduleConfig,
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


def plan_charge_window(
    *,
    result: CalculationResult,
    schedule_state: ScheduleState,
    schedule_config: TariffScheduleConfig,
    charging_current_a: float | None,
    nominal_voltage_v: float = 51.2,
    buffer_minutes: int = 15,
) -> ChargeSchedulePlan:
    """Calculate when grid charging must start to reach target SOC by window end."""
    tz = ZoneInfo(schedule_config.timezone)
    end_date = schedule_state.target_night_date
    start_date = (
        end_date - timedelta(days=1)
        if schedule_config.tariff_start >= schedule_config.tariff_end
        else end_date
    )
    window_start_at = datetime.combine(start_date, schedule_config.tariff_start, tzinfo=tz)
    window_end_at = datetime.combine(end_date, schedule_config.tariff_end, tzinfo=tz)

    if (
        not result.is_valid
        or result.target_soc_pct is None
        or result.current_soc_pct is None
        or result.config_snapshot is None
    ):
        return ChargeSchedulePlan(
            is_valid=False,
            reason="Target SOC or current SOC is unavailable.",
            charging_current_a=charging_current_a,
            nominal_voltage_v=nominal_voltage_v,
            charging_power_kw=None,
            estimated_duration_minutes=None,
            recommended_start_at=None,
            window_start_at=window_start_at,
            window_end_at=window_end_at,
            can_reach_target_in_window=None,
            should_charge_now=False,
        )

    if (
        charging_current_a is None
        or isinstance(charging_current_a, bool)
        or not math.isfinite(charging_current_a)
        or charging_current_a <= 0
    ):
        return ChargeSchedulePlan(
            is_valid=False,
            reason="charging_current_a must be a finite number > 0.",
            charging_current_a=charging_current_a,
            nominal_voltage_v=nominal_voltage_v,
            charging_power_kw=None,
            estimated_duration_minutes=None,
            recommended_start_at=None,
            window_start_at=window_start_at,
            window_end_at=window_end_at,
            can_reach_target_in_window=None,
            should_charge_now=False,
        )

    if not math.isfinite(nominal_voltage_v) or nominal_voltage_v <= 0 or buffer_minutes < 0:
        return ChargeSchedulePlan(
            is_valid=False,
            reason="Invalid nominal_voltage_v or buffer_minutes.",
            charging_current_a=charging_current_a,
            nominal_voltage_v=nominal_voltage_v,
            charging_power_kw=None,
            estimated_duration_minutes=None,
            recommended_start_at=None,
            window_start_at=window_start_at,
            window_end_at=window_end_at,
            can_reach_target_in_window=None,
            should_charge_now=False,
        )

    charging_power_kw = (float(charging_current_a) * float(nominal_voltage_v)) / 1000.0
    delta_soc = max(0.0, float(result.target_soc_pct) - float(result.current_soc_pct))

    if delta_soc <= 0.0:
        return ChargeSchedulePlan(
            is_valid=True,
            reason="Current SOC already meets or exceeds target SOC.",
            charging_current_a=float(charging_current_a),
            nominal_voltage_v=float(nominal_voltage_v),
            charging_power_kw=charging_power_kw,
            estimated_duration_minutes=0,
            recommended_start_at=window_end_at,
            window_start_at=window_start_at,
            window_end_at=window_end_at,
            can_reach_target_in_window=True,
            should_charge_now=False,
        )

    net_energy_kwh = (delta_soc / 100.0) * result.config_snapshot.usable_battery_kwh
    raw_minutes = (net_energy_kwh / charging_power_kw) * 60.0
    total_minutes = math.ceil(raw_minutes) + int(buffer_minutes)

    ideal_start = window_end_at - timedelta(minutes=total_minutes)
    can_reach = ideal_start >= window_start_at
    recommended_start_at = max(window_start_at, ideal_start)

    now_local = schedule_state.now_local
    should_charge_now = (
        schedule_state.in_tariff_window
        and now_local >= recommended_start_at
        and now_local < window_end_at
    )

    reason = (
        f"Need {total_minutes} min at {charging_power_kw:.2f} kW "
        f"({charging_current_a:.0f} A @ {nominal_voltage_v:.1f} V)."
    )
    if not can_reach:
        reason += " Warning: required duration exceeds tariff window."

    return ChargeSchedulePlan(
        is_valid=True,
        reason=reason,
        charging_current_a=float(charging_current_a),
        nominal_voltage_v=float(nominal_voltage_v),
        charging_power_kw=charging_power_kw,
        estimated_duration_minutes=total_minutes,
        recommended_start_at=recommended_start_at,
        window_start_at=window_start_at,
        window_end_at=window_end_at,
        can_reach_target_in_window=can_reach,
        should_charge_now=should_charge_now,
    )


def decide_program_soc_action(
    *,
    result: CalculationResult,
    schedule_state: ScheduleState,
    charge_plan: ChargeSchedulePlan,
    night_idle_soc: float,
    real_control_enabled: bool,
) -> tuple[int | None, str, str]:
    """Decide the desired Program 1 SOC and action label (pure, fail-safe).

    Returns ``(desired_soc_pct, action_name, reason)``.
    ``desired_soc_pct`` is ``None`` when no write/simulation target should be applied.
    """
    idle_soc = int(round(max(0.0, min(100.0, night_idle_soc))))

    if not schedule_state.in_tariff_window:
        return (
            idle_soc,
            "restore_idle_soc" if real_control_enabled else "simulate_idle_soc",
            "Outside economic tariff window; keep/restore night idle SOC.",
        )

    if not result.is_valid or result.target_soc_pct is None:
        return (
            None,
            "fail_safe_hold",
            f"Calculation invalid ({result.status_code.value}); refusing to order grid charge.",
        )

    if not charge_plan.is_valid:
        return (
            None,
            "fail_safe_hold",
            f"Charge plan invalid ({charge_plan.reason}); refusing to order grid charge.",
        )

    if charge_plan.should_charge_now:
        return (
            result.target_soc_pct,
            "apply_target_soc" if real_control_enabled else "simulate_target_soc",
            "Charge start time reached inside tariff window.",
        )

    return (
        idle_soc,
        "wait_idle_soc" if real_control_enabled else "simulate_wait_idle_soc",
        "Inside tariff window before recommended start time; allow night discharge to idle SOC.",
    )


def calculate_forecast_error(
    *,
    forecast_kwh: float | None,
    actual_production_kwh: float | None,
) -> tuple[float | None, float | None]:
    """Calculate forecast error (actual - forecast) in kWh and percentage."""
    if (
        forecast_kwh is None
        or actual_production_kwh is None
        or isinstance(forecast_kwh, bool)
        or isinstance(actual_production_kwh, bool)
        or not math.isfinite(forecast_kwh)
        or not math.isfinite(actual_production_kwh)
        or forecast_kwh < 0
        or actual_production_kwh < 0
    ):
        return None, None

    error_kwh = float(actual_production_kwh) - float(forecast_kwh)
    error_pct = (error_kwh / float(forecast_kwh) * 100.0) if forecast_kwh > 0 else None
    return round(error_kwh, 2), (round(error_pct, 1) if error_pct is not None else None)
