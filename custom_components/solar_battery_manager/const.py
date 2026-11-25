"""Constants for the Solar Battery Manager integration."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "solar_battery_manager"
STORAGE_VERSION = 1
STORAGE_KEY_PREFIX = f"{DOMAIN}_frozen_target"
DEFAULT_SCAN_INTERVAL = timedelta(minutes=5)

# Entity configuration keys
CONF_PV_FORECAST_ENTITY = "pv_forecast_entity"
CONF_LOAD_ENERGY_ENTITY = "load_energy_entity"
CONF_BATTERY_SOC_ENTITY = "battery_soc_entity"
CONF_GRID_CHARGE_CURRENT_ENTITY = "grid_charge_current_entity"
CONF_SUN_ENTITY = "sun_entity"

# Battery and calculation configuration keys
CONF_USABLE_BATTERY_KWH = "usable_battery_kwh"
CONF_CHARGE_EFFICIENCY = "charge_efficiency"
CONF_SAFETY_MARGIN_SOC = "safety_margin_soc"
CONF_MIN_OPERATIONAL_SOC = "min_operational_soc"
CONF_MAX_OPERATIONAL_SOC = "max_operational_soc"
CONF_BATTERY_NOMINAL_VOLTAGE = "battery_nominal_voltage"
CONF_CHARGE_TIME_BUFFER_MINUTES = "charge_time_buffer_minutes"

# Estimation and schedule keys
CONF_ESTIMATION_METHOD = "estimation_method"
CONF_LOOKBACK_DAYS = "lookback_days"
CONF_MIN_HISTORY_DAYS = "min_history_days"
CONF_SOLAR_WINDOW_START = "solar_window_start"
CONF_SOLAR_WINDOW_END = "solar_window_end"
CONF_TARIFF_START = "tariff_start"
CONF_TARIFF_END = "tariff_end"
CONF_FREEZE_TIME = "freeze_time"
CONF_SIMULATION_MODE = "simulation_mode"

# Defaults (read-only simulation in v1)
DEFAULT_USABLE_BATTERY_KWH = 12.0
DEFAULT_CHARGE_EFFICIENCY_PCT = 90.0
DEFAULT_SAFETY_MARGIN_SOC = 5.0
DEFAULT_MIN_OPERATIONAL_SOC = 15.0
DEFAULT_MAX_OPERATIONAL_SOC = 100.0
DEFAULT_BATTERY_NOMINAL_VOLTAGE = 51.2
DEFAULT_CHARGE_TIME_BUFFER_MINUTES = 15
DEFAULT_GRID_CHARGE_CURRENT_A = 25.0
DEFAULT_ESTIMATION_METHOD = "median"
DEFAULT_LOOKBACK_DAYS = 14
DEFAULT_MIN_HISTORY_DAYS = 3
DEFAULT_SOLAR_WINDOW_START = "08:00:00"
DEFAULT_SOLAR_WINDOW_END = "18:00:00"
DEFAULT_SUN_ENTITY = "sun.sun"
DEFAULT_TARIFF_START = "00:00:00"
DEFAULT_TARIFF_END = "08:00:00"
DEFAULT_FREEZE_TIME = "23:55:00"
DEFAULT_SIMULATION_MODE = True
