"""Diagnostics support for Solar Battery Manager."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .coordinator import SolarBatteryCoordinator


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for a config entry (without secrets)."""
    coordinator: SolarBatteryCoordinator = entry.runtime_data
    data = coordinator.data

    return {
        "entry_data": dict(entry.data),
        "entry_options": dict(entry.options),
        "real_control_enabled": coordinator.real_control_enabled,
        "simulation_mode": not coordinator.real_control_enabled,
        "is_frozen": data.is_frozen if data else None,
        "solar_window_paused": data.solar_window_paused if data else None,
        "charge_latched": data.charge_latched if data else None,
        "frozen_snapshots": coordinator.frozen_snapshots,
        "schedule_state": (
            {
                "now_local": data.schedule_state.now_local.isoformat(),
                "in_tariff_window": data.schedule_state.in_tariff_window,
                "is_freeze_active": data.schedule_state.is_freeze_active,
                "target_night_date": data.schedule_state.target_night_date.isoformat(),
            }
            if data
            else None
        ),
        "effective_result": (
            {
                "is_valid": data.effective_result.is_valid,
                "status_code": data.effective_result.status_code.value,
                "reason": data.effective_result.reason,
                "target_soc_pct": data.effective_result.target_soc_pct,
                "target_soc_raw": data.effective_result.target_soc_raw,
                "surplus_kwh": data.effective_result.surplus_kwh,
                "solar_soc_gain_pct": data.effective_result.solar_soc_gain_pct,
                "grid_energy_required_kwh": data.effective_result.grid_energy_required_kwh,
                "pv_forecast_kwh": data.effective_result.pv_forecast_kwh,
                "current_soc_pct": data.effective_result.current_soc_pct,
                "was_clamped": data.effective_result.was_clamped,
                "clamp_bound": data.effective_result.clamp_bound,
            }
            if data
            else None
        ),
        "charge_plan": (
            {
                "is_valid": data.charge_plan.is_valid,
                "reason": data.charge_plan.reason,
                "charging_current_a": data.charge_plan.charging_current_a,
                "charging_power_kw": data.charge_plan.charging_power_kw,
                "estimated_duration_minutes": data.charge_plan.estimated_duration_minutes,
                "recommended_start_at": (
                    data.charge_plan.recommended_start_at.isoformat()
                    if data.charge_plan.recommended_start_at
                    else None
                ),
                "can_reach_target_in_window": data.charge_plan.can_reach_target_in_window,
                "should_charge_now": data.charge_plan.should_charge_now,
            }
            if data
            else None
        ),
        "forecast_comparison": (
            asdict(data.forecast_comparison) if data else None
        ),
        "last_action": asdict(data.last_action) if data and data.last_action else None,
        "action_history": coordinator.action_history,
    }
