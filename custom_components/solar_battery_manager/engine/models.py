"""Data models for the pure Solar Battery Manager calculation engine."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, tzinfo
from enum import StrEnum
import math
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class EstimationMethod(StrEnum):
    """Supported daytime load estimation methods."""

    MEDIAN = "median"
    MEAN = "mean"


class CalculationStatus(StrEnum):
    """Outcome status codes for energy and SOC calculations."""

    OK = "ok"
    INVALID_CONFIG = "invalid_config"
    INVALID_PV_FORECAST = "invalid_pv_forecast"
    INVALID_CURRENT_SOC = "invalid_current_soc"
    INVALID_SUN_WINDOW = "invalid_sun_window"
    INSUFFICIENT_HISTORY = "insufficient_history"


def _is_finite_number(value: float | int | None) -> bool:
    """Return True if value is a finite real number (excluding bool)."""
    if value is None or isinstance(value, bool):
        return False
    return math.isfinite(float(value))


@dataclass(frozen=True, slots=True)
class BatteryConfig:
    """Configurable battery and calculation parameters.

    These parameters only govern the calculation model; they never modify
    inverter or BMS protection limits.
    """

    usable_battery_kwh: float
    charge_efficiency: float = 0.90
    grid_charge_efficiency: float | None = None
    safety_margin_soc: float = 5.0
    min_operational_soc: float = 10.0
    max_operational_soc: float = 100.0

    @property
    def effective_grid_efficiency(self) -> float:
        """Return efficiency used for grid charging calculations."""
        if self.grid_charge_efficiency is not None:
            return self.grid_charge_efficiency
        return self.charge_efficiency

    def validate(self) -> list[str]:
        """Validate battery configuration and return human-readable errors."""
        errors: list[str] = []

        if not _is_finite_number(self.usable_battery_kwh) or self.usable_battery_kwh <= 0:
            errors.append("usable_battery_kwh must be a finite number greater than 0.")

        if (
            not _is_finite_number(self.charge_efficiency)
            or self.charge_efficiency <= 0
            or self.charge_efficiency > 1.0
        ):
            errors.append("charge_efficiency must be in the range (0, 1.0].")

        if self.grid_charge_efficiency is not None and (
            not _is_finite_number(self.grid_charge_efficiency)
            or self.grid_charge_efficiency <= 0
            or self.grid_charge_efficiency > 1.0
        ):
            errors.append("grid_charge_efficiency must be in the range (0, 1.0].")

        if (
            not _is_finite_number(self.safety_margin_soc)
            or self.safety_margin_soc < 0
            or self.safety_margin_soc > 50.0
        ):
            errors.append("safety_margin_soc must be in the range [0, 50].")

        if (
            not _is_finite_number(self.min_operational_soc)
            or self.min_operational_soc < 0
            or self.min_operational_soc > 100.0
        ):
            errors.append("min_operational_soc must be in the range [0, 100].")

        if (
            not _is_finite_number(self.max_operational_soc)
            or self.max_operational_soc < 0
            or self.max_operational_soc > 100.0
        ):
            errors.append("max_operational_soc must be in the range [0, 100].")

        if (
            _is_finite_number(self.min_operational_soc)
            and _is_finite_number(self.max_operational_soc)
            and self.min_operational_soc > self.max_operational_soc
        ):
            errors.append("min_operational_soc cannot exceed max_operational_soc.")

        return errors


@dataclass(frozen=True, slots=True)
class DaytimeLoadSample:
    """Single day's house load during photovoltaic generation hours."""

    sample_date: date
    kwh: float | None
    is_valid: bool = True
    invalid_reason: str | None = None


@dataclass(frozen=True, slots=True)
class DiscardedSample:
    """Trace entry explaining why a historical sample was excluded."""

    sample_date: date
    kwh: float | None
    reason: str


@dataclass(frozen=True, slots=True)
class LoadEstimationResult:
    """Explainable result of daytime house load estimation."""

    is_valid: bool
    status_code: CalculationStatus
    reason: str
    estimated_kwh: float | None
    method: EstimationMethod
    samples_used: tuple[DaytimeLoadSample, ...]
    samples_discarded: tuple[DiscardedSample, ...]


@dataclass(frozen=True, slots=True)
class TariffScheduleConfig:
    """Economic tariff window and pre-midnight freeze schedule."""

    tariff_start: time = time(0, 0)
    tariff_end: time = time(8, 0)
    freeze_time: time = time(23, 55)
    timezone: str | tzinfo = "Europe/Madrid"

    def validate(self) -> list[str]:
        """Validate tariff schedule configuration."""
        errors: list[str] = []
        if self.tariff_start == self.tariff_end:
            errors.append("tariff_start and tariff_end cannot be equal.")
        if not isinstance(self.timezone, tzinfo):
            try:
                ZoneInfo(self.timezone)
            except ZoneInfoNotFoundError:
                errors.append(f"Unknown timezone: {self.timezone!r}.")
        return errors


@dataclass(frozen=True, slots=True)
class ScheduleState:
    """Evaluated state of the economic window and daily freeze."""

    now_local: datetime
    in_tariff_window: bool
    is_freeze_active: bool
    target_night_date: date


@dataclass(frozen=True, slots=True)
class ChargeSchedulePlan:
    """Explainable start-time plan based on max grid charging current."""

    is_valid: bool
    reason: str
    charging_current_a: float | None
    nominal_voltage_v: float
    charging_power_kw: float | None
    estimated_duration_minutes: int | None
    recommended_start_at: datetime | None
    window_start_at: datetime | None
    window_end_at: datetime | None
    can_reach_target_in_window: bool | None
    should_charge_now: bool


@dataclass(frozen=True, slots=True)
class CalculationResult:
    """Full, explainable output of a target SOC calculation."""

    is_valid: bool
    status_code: CalculationStatus
    reason: str
    target_soc_pct: int | None
    target_soc_raw: float | None
    surplus_kwh: float | None
    solar_soc_gain_pct: float | None
    grid_energy_required_kwh: float | None
    pv_forecast_kwh: float | None
    current_soc_pct: float | None
    load_estimation: LoadEstimationResult | None
    was_clamped: bool = False
    clamp_bound: str | None = None
    calculated_at: datetime | None = None
    target_night_date: date | None = None
    config_snapshot: BatteryConfig | None = None
