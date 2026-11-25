"""Diagnostics support for Solar Battery Manager."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import SolarBatteryCoordinator


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for a config entry (without secrets)."""
    coordinator: SolarBatteryCoordinator = hass.data[DOMAIN][entry.entry_id]
    data = coordinator.data

    return {
        "entry_data": dict(entry.data),
        "entry_options": dict(entry.options),
        "simulation_mode": coordinator.controller.is_simulation,
        "is_frozen": data.is_frozen if data else None,
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
        "last_action": asdict(data.last_action) if data and data.last_action else None,
    }
