"""Read-only sensor entities for Solar Battery Manager."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import CoordinatorData, SolarBatteryCoordinator
from .engine.models import CalculationStatus


@dataclass(frozen=True, kw_only=True)
class SolarBatterySensorDescription(SensorEntityDescription):
    """Describe a Solar Battery Manager sensor."""

    value_fn: Callable[[CoordinatorData], Any]
    attrs_fn: Callable[[CoordinatorData], dict[str, Any]] | None = None


def _target_soc_attrs(data: CoordinatorData) -> dict[str, Any]:
    res = data.effective_result
    cfg = res.config_snapshot
    return {
        "simulation_mode": data.simulation_mode,
        "is_frozen": data.is_frozen,
        "in_tariff_window": data.schedule_state.in_tariff_window,
        "target_night_date": res.target_night_date.isoformat() if res.target_night_date else None,
        "target_soc_raw": round(res.target_soc_raw, 2) if res.target_soc_raw is not None else None,
        "solar_soc_gain_pct": (
            round(res.solar_soc_gain_pct, 2) if res.solar_soc_gain_pct is not None else None
        ),
        "was_clamped": res.was_clamped,
        "clamp_bound": res.clamp_bound,
        "usable_battery_kwh": cfg.usable_battery_kwh if cfg else None,
        "charge_efficiency_pct": round(cfg.charge_efficiency * 100.0, 1) if cfg else None,
        "safety_margin_soc": cfg.safety_margin_soc if cfg else None,
        "status_code": res.status_code.value,
        "reason": res.reason,
        "calculated_at": res.calculated_at.isoformat() if res.calculated_at else None,
    }


def _load_forecast_attrs(data: CoordinatorData) -> dict[str, Any]:
    est = data.effective_result.load_estimation
    if est is None:
        return {}
    return {
        "estimation_method": est.method.value,
        "status_code": est.status_code.value,
        "reason": est.reason,
        "samples_used_count": len(est.samples_used),
        "samples_used": [
            {"date": s.sample_date.isoformat(), "kwh": s.kwh} for s in est.samples_used
        ],
        "samples_discarded_count": len(est.samples_discarded),
        "samples_discarded": [
            {"date": d.sample_date.isoformat(), "kwh": d.kwh, "reason": d.reason}
            for d in est.samples_discarded
        ],
    }


def _charge_plan_attrs(data: CoordinatorData) -> dict[str, Any]:
    plan = data.charge_plan
    return {
        "charging_current_a": plan.charging_current_a,
        "nominal_voltage_v": plan.nominal_voltage_v,
        "charging_power_kw": (
            round(plan.charging_power_kw, 2) if plan.charging_power_kw is not None else None
        ),
        "estimated_duration_minutes": plan.estimated_duration_minutes,
        "can_reach_target_in_window": plan.can_reach_target_in_window,
        "should_charge_now": plan.should_charge_now,
        "window_start_at": plan.window_start_at.isoformat() if plan.window_start_at else None,
        "window_end_at": plan.window_end_at.isoformat() if plan.window_end_at else None,
        "reason": plan.reason,
    }


def _forecast_error_attrs(data: CoordinatorData) -> dict[str, Any]:
    comp = data.forecast_comparison
    return {
        "forecast_for_today_kwh": comp.forecast_for_today_kwh,
        "actual_production_today_kwh": comp.actual_production_today_kwh,
        "forecast_error_pct": comp.forecast_error_pct,
        "frozen_target_soc_for_today": comp.frozen_target_soc_for_today,
    }


def _model_status_attrs(data: CoordinatorData) -> dict[str, Any]:
    action = data.last_action
    return {
        "reason": data.effective_result.reason,
        "simulation_mode": data.simulation_mode,
        "is_frozen": data.is_frozen,
        "solar_window_paused": data.solar_window_paused,
        "last_control_action": action.action if action else None,
        "last_control_soc_pct": action.target_soc_pct if action else None,
        "last_control_verified": action.verified if action else None,
        "last_control_reason": action.reason if action else None,
    }


SENSOR_DESCRIPTIONS: tuple[SolarBatterySensorDescription, ...] = (
    SolarBatterySensorDescription(
        key="pv_forecast_tomorrow",
        translation_key="pv_forecast_tomorrow",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=lambda d: (
            round(d.effective_result.pv_forecast_kwh, 2)
            if d.effective_result.pv_forecast_kwh is not None
            else None
        ),
    ),
    SolarBatterySensorDescription(
        key="load_forecast_tomorrow",
        translation_key="load_forecast_tomorrow",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=lambda d: (
            round(d.effective_result.load_estimation.estimated_kwh, 2)
            if d.effective_result.load_estimation
            and d.effective_result.load_estimation.estimated_kwh is not None
            else None
        ),
        attrs_fn=_load_forecast_attrs,
    ),
    SolarBatterySensorDescription(
        key="surplus_tomorrow",
        translation_key="surplus_tomorrow",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=lambda d: (
            round(d.effective_result.surplus_kwh, 2)
            if d.effective_result.surplus_kwh is not None
            else None
        ),
    ),
    SolarBatterySensorDescription(
        key="target_soc",
        translation_key="target_soc",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=lambda d: d.effective_result.target_soc_pct,
        attrs_fn=_target_soc_attrs,
    ),
    SolarBatterySensorDescription(
        key="grid_energy_required",
        translation_key="grid_energy_required",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=lambda d: (
            round(d.effective_result.grid_energy_required_kwh, 2)
            if d.effective_result.grid_energy_required_kwh is not None
            else None
        ),
    ),
    SolarBatterySensorDescription(
        key="recommended_charge_start",
        translation_key="recommended_charge_start",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda d: d.charge_plan.recommended_start_at,
        attrs_fn=_charge_plan_attrs,
    ),
    SolarBatterySensorDescription(
        key="forecast_error",
        translation_key="forecast_error",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.forecast_comparison.forecast_error_kwh,
        attrs_fn=_forecast_error_attrs,
    ),
    SolarBatterySensorDescription(
        key="model_status",
        translation_key="model_status",
        device_class=SensorDeviceClass.ENUM,
        options=[status.value for status in CalculationStatus],
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.effective_result.status_code.value,
        attrs_fn=_model_status_attrs,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Solar Battery Manager sensors from a config entry."""
    coordinator: SolarBatteryCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        SolarBatterySensor(coordinator, entry, description)
        for description in SENSOR_DESCRIPTIONS
    )


class SolarBatterySensor(CoordinatorEntity[SolarBatteryCoordinator], SensorEntity):
    """Read-only sensor entity for Solar Battery Manager."""

    entity_description: SolarBatterySensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SolarBatteryCoordinator,
        entry: ConfigEntry,
        description: SolarBatterySensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Solar Battery Manager",
            manufacturer="Solar Battery Manager",
            model="Simulation Mode (Read-Only)",
            sw_version="0.2.1",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def native_value(self) -> Any:
        """Return the current sensor value."""
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return explainability and diagnostic attributes."""
        if self.coordinator.data is None or self.entity_description.attrs_fn is None:
            return None
        return self.entity_description.attrs_fn(self.coordinator.data)
