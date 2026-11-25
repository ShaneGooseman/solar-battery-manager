"""Config flow and options flow for Solar Battery Manager."""

from __future__ import annotations

from datetime import time
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TimeSelector,
)

from .const import (
    CONF_BATTERY_NOMINAL_VOLTAGE,
    CONF_BATTERY_SOC_ENTITY,
    CONF_CHARGE_EFFICIENCY,
    CONF_CHARGE_TIME_BUFFER_MINUTES,
    CONF_ESTIMATION_METHOD,
    CONF_FREEZE_TIME,
    CONF_GRID_CHARGE_CURRENT_ENTITY,
    CONF_LOAD_ENERGY_ENTITY,
    CONF_LOOKBACK_DAYS,
    CONF_MAX_OPERATIONAL_SOC,
    CONF_MIN_HISTORY_DAYS,
    CONF_MIN_OPERATIONAL_SOC,
    CONF_PV_FORECAST_ENTITY,
    CONF_SAFETY_MARGIN_SOC,
    CONF_SOLAR_WINDOW_END,
    CONF_SOLAR_WINDOW_START,
    CONF_TARIFF_END,
    CONF_TARIFF_START,
    CONF_USABLE_BATTERY_KWH,
    DEFAULT_BATTERY_NOMINAL_VOLTAGE,
    DEFAULT_CHARGE_EFFICIENCY_PCT,
    DEFAULT_CHARGE_TIME_BUFFER_MINUTES,
    DEFAULT_ESTIMATION_METHOD,
    DEFAULT_FREEZE_TIME,
    DEFAULT_LOOKBACK_DAYS,
    DEFAULT_MAX_OPERATIONAL_SOC,
    DEFAULT_MIN_HISTORY_DAYS,
    DEFAULT_MIN_OPERATIONAL_SOC,
    DEFAULT_SAFETY_MARGIN_SOC,
    DEFAULT_SOLAR_WINDOW_END,
    DEFAULT_SOLAR_WINDOW_START,
    DEFAULT_TARIFF_END,
    DEFAULT_TARIFF_START,
    DEFAULT_USABLE_BATTERY_KWH,
    DOMAIN,
)
from .engine.models import BatteryConfig, EstimationMethod, TariffScheduleConfig


def _parse_time_str(value: str | time) -> time:
    """Parse HH:MM or HH:MM:SS string into datetime.time."""
    if isinstance(value, time):
        return value
    return time.fromisoformat(str(value))


def _validate_parameters(
    data: dict[str, Any],
    timezone_name: str,
) -> dict[str, str]:
    """Validate battery, estimation, and schedule parameters."""
    errors: dict[str, str] = {}

    battery_cfg = BatteryConfig(
        usable_battery_kwh=float(data[CONF_USABLE_BATTERY_KWH]),
        charge_efficiency=float(data[CONF_CHARGE_EFFICIENCY]) / 100.0,
        safety_margin_soc=float(data[CONF_SAFETY_MARGIN_SOC]),
        min_operational_soc=float(data[CONF_MIN_OPERATIONAL_SOC]),
        max_operational_soc=float(data[CONF_MAX_OPERATIONAL_SOC]),
    )
    if battery_cfg.validate():
        errors["base"] = "invalid_parameters"
        return errors

    lookback = int(data[CONF_LOOKBACK_DAYS])
    min_history = int(data[CONF_MIN_HISTORY_DAYS])
    if lookback <= 0 or min_history <= 0 or min_history > lookback:
        errors["base"] = "invalid_parameters"
        return errors

    try:
        solar_start = _parse_time_str(data[CONF_SOLAR_WINDOW_START])
        solar_end = _parse_time_str(data[CONF_SOLAR_WINDOW_END])
        tariff_start = _parse_time_str(data[CONF_TARIFF_START])
        tariff_end = _parse_time_str(data[CONF_TARIFF_END])
        freeze_time = _parse_time_str(data[CONF_FREEZE_TIME])
    except ValueError:
        errors["base"] = "invalid_schedule"
        return errors

    if solar_start >= solar_end:
        errors["base"] = "invalid_schedule"
        return errors

    schedule_cfg = TariffScheduleConfig(
        tariff_start=tariff_start,
        tariff_end=tariff_end,
        freeze_time=freeze_time,
        timezone=timezone_name,
    )
    if schedule_cfg.validate():
        errors["base"] = "invalid_schedule"

    return errors


def _entities_schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    """Build schema for selecting source entities."""
    defaults = defaults or {}
    return vol.Schema(
        {
            vol.Required(
                CONF_PV_FORECAST_ENTITY,
                default=defaults.get(CONF_PV_FORECAST_ENTITY),
            ): EntitySelector(EntitySelectorConfig(domain="sensor")),
            vol.Required(
                CONF_LOAD_ENERGY_ENTITY,
                default=defaults.get(CONF_LOAD_ENERGY_ENTITY),
            ): EntitySelector(EntitySelectorConfig(domain="sensor")),
            vol.Required(
                CONF_BATTERY_SOC_ENTITY,
                default=defaults.get(CONF_BATTERY_SOC_ENTITY),
            ): EntitySelector(EntitySelectorConfig(domain="sensor")),
            vol.Optional(
                CONF_GRID_CHARGE_CURRENT_ENTITY,
                default=defaults.get(CONF_GRID_CHARGE_CURRENT_ENTITY),
            ): EntitySelector(EntitySelectorConfig(domain=["number", "sensor"])),
        }
    )


def _parameters_schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    """Build schema for battery, estimation, and schedule parameters."""
    defaults = defaults or {}
    return vol.Schema(
        {
            vol.Required(
                CONF_USABLE_BATTERY_KWH,
                default=defaults.get(CONF_USABLE_BATTERY_KWH, DEFAULT_USABLE_BATTERY_KWH),
            ): NumberSelector(
                NumberSelectorConfig(min=1.0, max=200.0, step=0.1, mode=NumberSelectorMode.BOX)
            ),
            vol.Required(
                CONF_CHARGE_EFFICIENCY,
                default=defaults.get(CONF_CHARGE_EFFICIENCY, DEFAULT_CHARGE_EFFICIENCY_PCT),
            ): NumberSelector(
                NumberSelectorConfig(min=50.0, max=100.0, step=1.0, mode=NumberSelectorMode.BOX)
            ),
            vol.Required(
                CONF_SAFETY_MARGIN_SOC,
                default=defaults.get(CONF_SAFETY_MARGIN_SOC, DEFAULT_SAFETY_MARGIN_SOC),
            ): NumberSelector(
                NumberSelectorConfig(min=0.0, max=30.0, step=1.0, mode=NumberSelectorMode.BOX)
            ),
            vol.Required(
                CONF_MIN_OPERATIONAL_SOC,
                default=defaults.get(CONF_MIN_OPERATIONAL_SOC, DEFAULT_MIN_OPERATIONAL_SOC),
            ): NumberSelector(
                NumberSelectorConfig(min=0.0, max=90.0, step=1.0, mode=NumberSelectorMode.BOX)
            ),
            vol.Required(
                CONF_MAX_OPERATIONAL_SOC,
                default=defaults.get(CONF_MAX_OPERATIONAL_SOC, DEFAULT_MAX_OPERATIONAL_SOC),
            ): NumberSelector(
                NumberSelectorConfig(min=50.0, max=100.0, step=1.0, mode=NumberSelectorMode.BOX)
            ),
            vol.Required(
                CONF_BATTERY_NOMINAL_VOLTAGE,
                default=defaults.get(CONF_BATTERY_NOMINAL_VOLTAGE, DEFAULT_BATTERY_NOMINAL_VOLTAGE),
            ): NumberSelector(
                NumberSelectorConfig(min=12.0, max=100.0, step=0.1, mode=NumberSelectorMode.BOX)
            ),
            vol.Required(
                CONF_CHARGE_TIME_BUFFER_MINUTES,
                default=defaults.get(
                    CONF_CHARGE_TIME_BUFFER_MINUTES, DEFAULT_CHARGE_TIME_BUFFER_MINUTES
                ),
            ): NumberSelector(
                NumberSelectorConfig(min=0, max=120, step=5, mode=NumberSelectorMode.BOX)
            ),
            vol.Required(
                CONF_ESTIMATION_METHOD,
                default=defaults.get(CONF_ESTIMATION_METHOD, DEFAULT_ESTIMATION_METHOD),
            ): SelectSelector(
                SelectSelectorConfig(
                    options=[EstimationMethod.MEDIAN.value, EstimationMethod.MEAN.value],
                    mode=SelectSelectorMode.DROPDOWN,
                    translation_key="estimation_method",
                )
            ),
            vol.Required(
                CONF_LOOKBACK_DAYS,
                default=defaults.get(CONF_LOOKBACK_DAYS, DEFAULT_LOOKBACK_DAYS),
            ): NumberSelector(
                NumberSelectorConfig(min=3, max=60, step=1, mode=NumberSelectorMode.BOX)
            ),
            vol.Required(
                CONF_MIN_HISTORY_DAYS,
                default=defaults.get(CONF_MIN_HISTORY_DAYS, DEFAULT_MIN_HISTORY_DAYS),
            ): NumberSelector(
                NumberSelectorConfig(min=1, max=30, step=1, mode=NumberSelectorMode.BOX)
            ),
            vol.Required(
                CONF_SOLAR_WINDOW_START,
                default=defaults.get(CONF_SOLAR_WINDOW_START, DEFAULT_SOLAR_WINDOW_START),
            ): TimeSelector(),
            vol.Required(
                CONF_SOLAR_WINDOW_END,
                default=defaults.get(CONF_SOLAR_WINDOW_END, DEFAULT_SOLAR_WINDOW_END),
            ): TimeSelector(),
            vol.Required(
                CONF_TARIFF_START,
                default=defaults.get(CONF_TARIFF_START, DEFAULT_TARIFF_START),
            ): TimeSelector(),
            vol.Required(
                CONF_TARIFF_END,
                default=defaults.get(CONF_TARIFF_END, DEFAULT_TARIFF_END),
            ): TimeSelector(),
            vol.Required(
                CONF_FREEZE_TIME,
                default=defaults.get(CONF_FREEZE_TIME, DEFAULT_FREEZE_TIME),
            ): TimeSelector(),
        }
    )


class SolarBatteryManagerConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Solar Battery Manager."""

    VERSION = 1

    def __init__(self) -> None:
        self._entity_data: dict[str, Any] = {}

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Step 1: select existing Home Assistant entities."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        errors: dict[str, str] = {}
        if user_input is not None:
            for key in (
                CONF_PV_FORECAST_ENTITY,
                CONF_LOAD_ENERGY_ENTITY,
                CONF_BATTERY_SOC_ENTITY,
            ):
                entity_id = user_input.get(key)
                if not entity_id or self.hass.states.get(entity_id) is None:
                    errors["base"] = "invalid_entity"
                    break

            if not errors:
                self._entity_data = user_input
                return await self.async_step_parameters()

        return self.async_show_form(
            step_id="user",
            data_schema=_entities_schema(user_input),
            errors=errors,
        )

    async def async_step_parameters(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Step 2: configure battery, estimation, and tariff schedule."""
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = _validate_parameters(user_input, self.hass.config.time_zone)
            if not errors:
                full_data = {**self._entity_data, **user_input}
                return self.async_create_entry(
                    title="Solar Battery Manager (Simulation)",
                    data=full_data,
                )

        return self.async_show_form(
            step_id="parameters",
            data_schema=_parameters_schema(user_input),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> SolarBatteryManagerOptionsFlow:
        """Return the options flow."""
        return SolarBatteryManagerOptionsFlow()


class SolarBatteryManagerOptionsFlow(OptionsFlow):
    """Handle options flow for Solar Battery Manager."""

    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Manage the options."""
        errors: dict[str, str] = {}
        merged = {**self.config_entry.data, **self.config_entry.options}

        if user_input is not None:
            errors = _validate_parameters(user_input, self.hass.config.time_zone)
            if not errors:
                return self.async_create_entry(title="", data=user_input)

        schema = vol.Schema(
            {
                **_entities_schema(merged).schema,
                **_parameters_schema(merged).schema,
            }
        )
        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            errors=errors,
        )
