"""Opt-in switch entity to enable or disable real inverter control."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_DEYE_PROGRAM_SOC_ENTITY, DOMAIN
from .coordinator import SolarBatteryCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Solar Battery Manager switch entities."""
    coordinator: SolarBatteryCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([SolarBatteryRealControlSwitch(coordinator, entry)])


class SolarBatteryRealControlSwitch(
    CoordinatorEntity[SolarBatteryCoordinator],
    SwitchEntity,
):
    """Master opt-in switch for real Deye Program SOC control (OFF by default)."""

    _attr_has_entity_name = True
    _attr_translation_key = "real_control"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator: SolarBatteryCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_real_control"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Solar Battery Manager",
            manufacturer="Solar Battery Manager",
            model="Simulation Mode (Read-Only)",
            sw_version="0.2.0",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def is_on(self) -> bool:
        """Return True only when real inverter control is explicitly enabled."""
        return self.coordinator.real_control_enabled

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable real Deye Program SOC control (requires configured target entity)."""
        await self.coordinator.async_set_real_control_enabled(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable real control and return immediately to read-only simulation."""
        await self.coordinator.async_set_real_control_enabled(False)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose target entity and safety status."""
        target_entity = self._entry.options.get(
            CONF_DEYE_PROGRAM_SOC_ENTITY,
            self._entry.data.get(CONF_DEYE_PROGRAM_SOC_ENTITY),
        )
        return {
            "target_entity": target_entity,
            "simulation_mode": not self.coordinator.real_control_enabled,
        }
