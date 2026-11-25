"""Pure calculation engine for Solar Battery Manager."""

from .calculator import calculate_target_soc, plan_charge_window
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
from .schedule import evaluate_schedule

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
    "calculate_target_soc",
    "estimate_daytime_load",
    "evaluate_schedule",
    "plan_charge_window",
]
