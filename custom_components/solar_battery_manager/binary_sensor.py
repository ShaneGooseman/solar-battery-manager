"""Read-only binary sensor entities for Solar Battery Manager."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SolarBatteryCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Solar Battery Manager binary sensors."""
    coordinator: SolarBatteryCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([SolarBatteryReadyBinarySensor(coordinator, entry)])


class SolarBatteryReadyBinarySensor(
    CoordinatorEntity[SolarBatteryCoordinator],
    BinarySensorEntity,
):
    """Indicates whether the target SOC calculation is valid and ready."""

    _attr_has_entity_name = True
    _attr_name = "Calculation ready"
    _attr_device_class = BinarySensorDeviceClass.RUNNING

    def __init__(
        self,
        coordinator: SolarBatteryCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_ready"

    @property
    def is_on(self) -> bool | None:
        """Return True only when the effective calculation is valid."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.effective_result.is_valid
