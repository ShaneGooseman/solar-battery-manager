"""Pure calculation engine for Solar Battery Manager."""

from .calculator import (
    calculate_forecast_error,
    calculate_target_soc,
    decide_program_soc_action,
    plan_charge_window,
)
from .estimator import estimate_daytime_load
from .models import (
    BatteryConfig,
    CalculationResult,
    CalculationStatus,
    ChargeSchedulePlan,
    DaytimeLoadSample,
    DiscardedSample,
    EstimationMethod,
    LoadEstimationResult,
    ScheduleState,
    TariffScheduleConfig,
)
from .schedule import evaluate_schedule, is_within_solar_window

__all__ = [
    "BatteryConfig",
    "CalculationResult",
    "CalculationStatus",
    "ChargeSchedulePlan",
    "DaytimeLoadSample",
    "DiscardedSample",
    "EstimationMethod",
    "LoadEstimationResult",
    "ScheduleState",
    "TariffScheduleConfig",
    "calculate_forecast_error",
    "calculate_target_soc",
    "decide_program_soc_action",
    "estimate_daytime_load",
    "evaluate_schedule",
    "is_within_solar_window",
    "plan_charge_window",
]
