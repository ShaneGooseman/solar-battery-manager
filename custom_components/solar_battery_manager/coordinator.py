"""DataUpdateCoordinator and daily target freeze persistence for Solar Battery Manager."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timezone
import logging
import math
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN, UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    CONF_BATTERY_NOMINAL_VOLTAGE,
    CONF_BATTERY_SOC_ENTITY,
    CONF_CHARGE_EFFICIENCY,
    CONF_CHARGE_TIME_BUFFER_MINUTES,
    CONF_DEYE_PROGRAM_SOC_ENTITY,
    CONF_ESTIMATION_METHOD,
    CONF_FREEZE_TIME,
    CONF_GRID_CHARGE_CURRENT_ENTITY,
    CONF_LOAD_ENERGY_ENTITY,
    CONF_LOOKBACK_DAYS,
    CONF_MAX_OPERATIONAL_SOC,
    CONF_MIN_HISTORY_DAYS,
    CONF_MIN_OPERATIONAL_SOC,
    CONF_NIGHT_IDLE_SOC,
    CONF_PV_FORECAST_ENTITY,
    CONF_PV_PRODUCTION_TODAY_ENTITY,
    CONF_SAFETY_MARGIN_SOC,
    CONF_SUN_ENTITY,
    CONF_TARIFF_END,
    CONF_TARIFF_START,
    CONF_USABLE_BATTERY_KWH,
    DEFAULT_BATTERY_NOMINAL_VOLTAGE,
    DEFAULT_CHARGE_EFFICIENCY_PCT,
    DEFAULT_CHARGE_TIME_BUFFER_MINUTES,
    DEFAULT_ESTIMATION_METHOD,
    DEFAULT_FREEZE_TIME,
    DEFAULT_GRID_CHARGE_CURRENT_A,
    DEFAULT_LOOKBACK_DAYS,
    DEFAULT_MAX_OPERATIONAL_SOC,
    DEFAULT_MIN_HISTORY_DAYS,
    DEFAULT_MIN_OPERATIONAL_SOC,
    DEFAULT_NIGHT_IDLE_SOC,
    DEFAULT_SAFETY_MARGIN_SOC,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SUN_ENTITY,
    DEFAULT_TARIFF_END,
    DEFAULT_TARIFF_START,
    DEFAULT_USABLE_BATTERY_KWH,
    DOMAIN,
    STORAGE_KEY_PREFIX,
    STORAGE_VERSION,
)
from .control import (
    ControlActionRecord,
    DeyeProgramSocController,
    InverterController,
    ReadOnlySimulationController,
)
from .engine.calculator import (
    calculate_forecast_error,
    calculate_target_soc,
    decide_program_soc_action,
    plan_charge_window,
)
from .engine.models import (
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
from .engine.schedule import evaluate_schedule
from .history import async_fetch_daytime_load_history, resolve_solar_window_from_sun

_LOGGER = logging.getLogger(__name__)


def _parse_float_state(hass: HomeAssistant, entity_id: str) -> tuple[float | None, str | None, str | None]:
    """Read numeric state and unit from Home Assistant without throwing."""
    state_obj = hass.states.get(entity_id)
    if state_obj is None:
        return None, None, f"entity_missing:{entity_id}"
    if state_obj.state in (STATE_UNKNOWN, STATE_UNAVAILABLE, "", None):
        return None, None, f"entity_{state_obj.state}:{entity_id}"
    try:
        value = float(state_obj.state)
    except (TypeError, ValueError):
        return None, None, f"non_numeric_state:{entity_id}"
    if not math.isfinite(value):
        return None, None, f"non_finite_state:{entity_id}"
    unit = state_obj.attributes.get("unit_of_measurement")
    return value, str(unit) if unit is not None else None, None


def _energy_unit_scale(unit: str | None) -> float | None:
    """Return multiplier to convert sensor energy unit to kWh, or None if unsupported."""
    if unit in (None, UnitOfEnergy.KILO_WATT_HOUR, "kWh"):
        return 1.0
    if unit in (UnitOfEnergy.WATT_HOUR, "Wh"):
        return 0.001
    return None


@dataclass(frozen=True, slots=True)
class ForecastComparison:
    """Comparison between yesterday's frozen forecast for today and actual PV today."""

    forecast_for_today_kwh: float | None
    actual_production_today_kwh: float | None
    forecast_error_kwh: float | None
    forecast_error_pct: float | None
    frozen_target_soc_for_today: int | None


@dataclass(frozen=True, slots=True)
class CoordinatorData:
    """Snapshot exposed by the coordinator to integration entities."""

    live_result: CalculationResult
    effective_result: CalculationResult
    schedule_state: ScheduleState
    charge_plan: ChargeSchedulePlan
    forecast_comparison: ForecastComparison
    is_frozen: bool
    simulation_mode: bool
    last_action: ControlActionRecord | None


class SolarBatteryCoordinator(DataUpdateCoordinator[CoordinatorData]):
    """Coordinator that computes, freezes, and optionally applies target SOC."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=DEFAULT_SCAN_INTERVAL,
        )
        self.entry = entry
        self._sim_controller = ReadOnlySimulationController()
        self._store: Store[dict[str, Any]] = Store(
            hass,
            STORAGE_VERSION,
            f"{STORAGE_KEY_PREFIX}_{entry.entry_id}",
        )
        self._storage_loaded = False
        self._frozen_by_date: dict[str, dict[str, Any]] = {}
        self._real_control_enabled = False

    @property
    def real_control_enabled(self) -> bool:
        """Return True only when user has explicitly enabled real Deye control."""
        return self._real_control_enabled

    def _cfg(self, key: str, default: Any = None) -> Any:
        if key in self.entry.options:
            return self.entry.options[key]
        return self.entry.data.get(key, default)

    async def async_load_storage(self) -> None:
        """Load persisted frozen targets and opt-in switch state."""
        stored = await self._store.async_load()
        self._storage_loaded = True
        if not isinstance(stored, dict):
            return

        self._real_control_enabled = bool(stored.get("real_control_enabled", False))
        frozen_by_date = stored.get("frozen_by_date")
        if isinstance(frozen_by_date, dict):
            self._frozen_by_date = dict(frozen_by_date)
        elif "target_night_date" in stored:
            # Backward compatibility with v0.1.x single-snapshot format
            key = str(stored["target_night_date"])
            self._frozen_by_date[key] = stored

    async def _async_save_storage(self) -> None:
        """Persist storage payload (keeping the last 7 daily frozen snapshots)."""
        sorted_keys = sorted(self._frozen_by_date.keys())[-7:]
        trimmed = {k: self._frozen_by_date[k] for k in sorted_keys}
        self._frozen_by_date = trimmed
        await self._store.async_save(
            {
                "real_control_enabled": self._real_control_enabled,
                "frozen_by_date": trimmed,
            }
        )

    async def async_set_real_control_enabled(self, enabled: bool) -> None:
        """Enable or disable opt-in real Deye Program SOC control."""
        if enabled:
            target_entity = self._cfg(CONF_DEYE_PROGRAM_SOC_ENTITY)
            if not target_entity or self.hass.states.get(str(target_entity)) is None:
                raise HomeAssistantError(
                    "Configure a valid Deye Program SOC number entity in integration options before enabling real control."
                )

        self._real_control_enabled = enabled
        await self._async_save_storage()
        await self.async_request_refresh()

    async def _async_save_frozen(self, result: CalculationResult) -> None:
        """Persist frozen daily target SOC to survive restarts and midnight resets."""
        if not result.is_valid or result.target_soc_pct is None or result.target_night_date is None:
            return

        date_key = result.target_night_date.isoformat()
        self._frozen_by_date[date_key] = {
            "target_night_date": date_key,
            "target_soc_pct": result.target_soc_pct,
            "target_soc_raw": result.target_soc_raw,
            "surplus_kwh": result.surplus_kwh,
            "solar_soc_gain_pct": result.solar_soc_gain_pct,
            "pv_forecast_kwh": result.pv_forecast_kwh,
            "daytime_load_forecast_kwh": (
                result.load_estimation.estimated_kwh if result.load_estimation else None
            ),
            "estimation_method": (
                result.load_estimation.method.value if result.load_estimation else None
            ),
            "was_clamped": result.was_clamped,
            "clamp_bound": result.clamp_bound,
            "calculated_at": result.calculated_at.isoformat() if result.calculated_at else None,
        }
        await self._async_save_storage()

    def _restore_frozen_result(
        self,
        *,
        target_night_date: date,
        current_soc_pct: float | None,
        battery_cfg: BatteryConfig,
    ) -> CalculationResult | None:
        """Return persisted frozen CalculationResult if it matches target_night_date."""
        snapshot = self._frozen_by_date.get(target_night_date.isoformat())
        if not snapshot:
            return None

        target_soc_pct = snapshot.get("target_soc_pct")
        if not isinstance(target_soc_pct, int):
            return None

        grid_energy_required: float | None = None
        if current_soc_pct is not None:
            delta_soc = max(0.0, float(target_soc_pct) - float(current_soc_pct))
            grid_energy_required = (
                (delta_soc / 100.0) * battery_cfg.usable_battery_kwh
            ) / battery_cfg.effective_grid_efficiency

        est_kwh = snapshot.get("daytime_load_forecast_kwh")
        method_raw = snapshot.get("estimation_method", DEFAULT_ESTIMATION_METHOD)
        load_est = LoadEstimationResult(
            is_valid=True,
            status_code=CalculationStatus.OK,
            reason="Restored from frozen pre-midnight snapshot.",
            estimated_kwh=float(est_kwh) if est_kwh is not None else None,
            method=EstimationMethod(method_raw),
            samples_used=(),
            samples_discarded=(),
        )
        calc_at_raw = snapshot.get("calculated_at")
        calc_at = datetime.fromisoformat(calc_at_raw) if calc_at_raw else None

        return CalculationResult(
            is_valid=True,
            status_code=CalculationStatus.OK,
            reason="Using frozen pre-midnight target SOC for active overnight window.",
            target_soc_pct=target_soc_pct,
            target_soc_raw=snapshot.get("target_soc_raw"),
            surplus_kwh=snapshot.get("surplus_kwh"),
            solar_soc_gain_pct=snapshot.get("solar_soc_gain_pct"),
            grid_energy_required_kwh=grid_energy_required,
            pv_forecast_kwh=snapshot.get("pv_forecast_kwh"),
            current_soc_pct=current_soc_pct,
            load_estimation=load_est,
            was_clamped=bool(snapshot.get("was_clamped", False)),
            clamp_bound=snapshot.get("clamp_bound"),
            calculated_at=calc_at,
            target_night_date=target_night_date,
            config_snapshot=battery_cfg,
        )

    def _active_controller(self) -> InverterController:
        """Return real Deye controller only when opt-in switch is ON and configured."""
        if self._real_control_enabled:
            deye_entity = self._cfg(CONF_DEYE_PROGRAM_SOC_ENTITY)
            if deye_entity:
                return DeyeProgramSocController(self.hass, str(deye_entity))
        return self._sim_controller

    async def _async_update_data(self) -> CoordinatorData:
        """Fetch sensor states, recorder history, and compute target SOC."""
        if not self._storage_loaded:
            await self.async_load_storage()

        now_utc = datetime.now(timezone.utc)
        battery_cfg = BatteryConfig(
            usable_battery_kwh=float(self._cfg(CONF_USABLE_BATTERY_KWH, DEFAULT_USABLE_BATTERY_KWH)),
            charge_efficiency=float(self._cfg(CONF_CHARGE_EFFICIENCY, DEFAULT_CHARGE_EFFICIENCY_PCT))
            / 100.0,
            safety_margin_soc=float(self._cfg(CONF_SAFETY_MARGIN_SOC, DEFAULT_SAFETY_MARGIN_SOC)),
            min_operational_soc=float(
                self._cfg(CONF_MIN_OPERATIONAL_SOC, DEFAULT_MIN_OPERATIONAL_SOC)
            ),
            max_operational_soc=float(
                self._cfg(CONF_MAX_OPERATIONAL_SOC, DEFAULT_MAX_OPERATIONAL_SOC)
            ),
        )

        schedule_cfg = TariffScheduleConfig(
            tariff_start=time.fromisoformat(str(self._cfg(CONF_TARIFF_START, DEFAULT_TARIFF_START))),
            tariff_end=time.fromisoformat(str(self._cfg(CONF_TARIFF_END, DEFAULT_TARIFF_END))),
            freeze_time=time.fromisoformat(str(self._cfg(CONF_FREEZE_TIME, DEFAULT_FREEZE_TIME))),
            timezone=self.hass.config.time_zone,
        )
        schedule_state = evaluate_schedule(now_utc, schedule_cfg)

        pv_entity = str(self._cfg(CONF_PV_FORECAST_ENTITY))
        load_entity = str(self._cfg(CONF_LOAD_ENERGY_ENTITY))
        soc_entity = str(self._cfg(CONF_BATTERY_SOC_ENTITY))

        pv_raw, pv_unit, pv_err = _parse_float_state(self.hass, pv_entity)
        pv_scale = _energy_unit_scale(pv_unit)
        pv_forecast_kwh: float | None = None
        if pv_err is None and pv_raw is not None and pv_scale is not None:
            pv_forecast_kwh = pv_raw * pv_scale

        current_soc_pct, _, _ = _parse_float_state(self.hass, soc_entity)

        load_state = self.hass.states.get(load_entity)
        load_unit = load_state.attributes.get("unit_of_measurement") if load_state else None
        load_scale = _energy_unit_scale(str(load_unit) if load_unit is not None else None)

        lookback_days = int(self._cfg(CONF_LOOKBACK_DAYS, DEFAULT_LOOKBACK_DAYS))
        min_history_days = int(self._cfg(CONF_MIN_HISTORY_DAYS, DEFAULT_MIN_HISTORY_DAYS))
        method = EstimationMethod(
            str(self._cfg(CONF_ESTIMATION_METHOD, DEFAULT_ESTIMATION_METHOD))
        )

        sun_entity = str(self._cfg(CONF_SUN_ENTITY, DEFAULT_SUN_ENTITY))
        sun_state = self.hass.states.get(sun_entity)
        sun_err: str | None = None
        solar_start: time | None = None
        solar_end: time | None = None

        if sun_state is None or sun_state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            sun_err = f"Sun entity '{sun_entity}' is missing or unavailable."
        else:
            solar_start, solar_end, sun_err_code = resolve_solar_window_from_sun(
                sun_state.attributes.get("next_rising"),
                sun_state.attributes.get("next_setting"),
                self.hass.config.time_zone,
            )
            if sun_err_code is not None:
                sun_err = f"Sun entity '{sun_entity}' error: {sun_err_code}."

        load_samples: list[DaytimeLoadSample] = []
        if sun_err is None and load_scale is not None and solar_start is not None and solar_end is not None:
            load_samples = await async_fetch_daytime_load_history(
                self.hass,
                entity_id=load_entity,
                solar_start=solar_start,
                solar_end=solar_end,
                timezone_name=self.hass.config.time_zone,
                lookback_days=lookback_days,
                unit_scale_to_kwh=load_scale,
                now=now_utc,
            )

        if sun_err is not None:
            live_result = CalculationResult(
                is_valid=False,
                status_code=CalculationStatus.INVALID_SUN_WINDOW,
                reason=sun_err,
                target_soc_pct=None,
                target_soc_raw=None,
                surplus_kwh=None,
                solar_soc_gain_pct=None,
                grid_energy_required_kwh=None,
                pv_forecast_kwh=pv_forecast_kwh,
                current_soc_pct=current_soc_pct,
                load_estimation=None,
                calculated_at=schedule_state.now_local,
                target_night_date=schedule_state.target_night_date,
                config_snapshot=battery_cfg,
            )
        else:
            live_result = calculate_target_soc(
                pv_forecast_kwh=pv_forecast_kwh,
                load_samples=load_samples,
                config=battery_cfg,
                current_soc_pct=current_soc_pct,
                estimation_method=method,
                lookback_days=lookback_days,
                min_history_days=min_history_days,
                calculated_at=schedule_state.now_local,
                target_night_date=schedule_state.target_night_date,
            )

        is_frozen = False
        effective_result = live_result

        if schedule_state.is_freeze_active:
            frozen = self._restore_frozen_result(
                target_night_date=schedule_state.target_night_date,
                current_soc_pct=current_soc_pct,
                battery_cfg=battery_cfg,
            )
            if frozen is not None:
                effective_result = frozen
                is_frozen = True
            elif live_result.is_valid:
                await self._async_save_frozen(live_result)
                is_frozen = True

        current_entity = self._cfg(CONF_GRID_CHARGE_CURRENT_ENTITY)
        if current_entity:
            charging_current_a, _, _ = _parse_float_state(self.hass, str(current_entity))
        else:
            charging_current_a = DEFAULT_GRID_CHARGE_CURRENT_A

        nominal_voltage_v = float(
            self._cfg(CONF_BATTERY_NOMINAL_VOLTAGE, DEFAULT_BATTERY_NOMINAL_VOLTAGE)
        )
        buffer_minutes = int(
            self._cfg(CONF_CHARGE_TIME_BUFFER_MINUTES, DEFAULT_CHARGE_TIME_BUFFER_MINUTES)
        )
        charge_plan = plan_charge_window(
            result=effective_result,
            schedule_state=schedule_state,
            schedule_config=schedule_cfg,
            charging_current_a=charging_current_a,
            nominal_voltage_v=nominal_voltage_v,
            buffer_minutes=buffer_minutes,
        )

        night_idle_soc = float(self._cfg(CONF_NIGHT_IDLE_SOC, DEFAULT_NIGHT_IDLE_SOC))
        controller = self._active_controller()
        desired_soc, action_name, action_reason = decide_program_soc_action(
            result=effective_result,
            schedule_state=schedule_state,
            charge_plan=charge_plan,
            night_idle_soc=night_idle_soc,
            real_control_enabled=not controller.is_simulation,
        )
        last_action = await controller.async_apply_program_soc(
            action=action_name,
            target_soc_pct=desired_soc,
            reason=action_reason,
            now=schedule_state.now_local,
        )

        # Forecast vs actual comparison for today (using yesterday's frozen snapshot)
        today_key = schedule_state.now_local.date().isoformat()
        today_snapshot = self._frozen_by_date.get(today_key, {})
        forecast_today_raw = today_snapshot.get("pv_forecast_kwh")
        forecast_today_kwh = (
            float(forecast_today_raw) if forecast_today_raw is not None else None
        )
        frozen_target_today = today_snapshot.get("target_soc_pct")

        actual_today_kwh: float | None = None
        prod_today_entity = self._cfg(CONF_PV_PRODUCTION_TODAY_ENTITY)
        if prod_today_entity:
            prod_raw, prod_unit, prod_err = _parse_float_state(self.hass, str(prod_today_entity))
            prod_scale = _energy_unit_scale(prod_unit)
            if prod_err is None and prod_raw is not None and prod_scale is not None:
                actual_today_kwh = round(prod_raw * prod_scale, 2)

        error_kwh, error_pct = calculate_forecast_error(
            forecast_kwh=forecast_today_kwh,
            actual_production_kwh=actual_today_kwh,
        )
        forecast_comparison = ForecastComparison(
            forecast_for_today_kwh=forecast_today_kwh,
            actual_production_today_kwh=actual_today_kwh,
            forecast_error_kwh=error_kwh,
            forecast_error_pct=error_pct,
            frozen_target_soc_for_today=(
                int(frozen_target_today) if isinstance(frozen_target_today, int) else None
            ),
        )

        return CoordinatorData(
            live_result=live_result,
            effective_result=effective_result,
            schedule_state=schedule_state,
            charge_plan=charge_plan,
            forecast_comparison=forecast_comparison,
            is_frozen=is_frozen,
            simulation_mode=controller.is_simulation,
            last_action=last_action,
        )
