"""Interchangeable inverter control abstraction (read-only simulation in v1)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import logging
from typing import Protocol

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ControlActionRecord:
    """Audit record of a simulated or real control decision."""

    timestamp: datetime
    action: str
    target_soc_pct: int | None
    simulated: bool
    reason: str


class InverterController(Protocol):
    """Protocol for inverter control adapters."""

    @property
    def is_simulation(self) -> bool:
        """Return True when running in read-only simulation mode."""

    async def async_apply_target_soc(
        self,
        target_soc_pct: int,
        reason: str,
        now: datetime,
    ) -> ControlActionRecord:
        """Apply or simulate a target SOC decision."""

    async def async_stop_charge(
        self,
        reason: str,
        now: datetime,
    ) -> ControlActionRecord:
        """Stop or simulate stopping grid charge."""


class ReadOnlySimulationController:
    """Read-only simulation controller that never writes to any inverter entity."""

    def __init__(self) -> None:
        self._last_action: ControlActionRecord | None = None

    @property
    def is_simulation(self) -> bool:
        """Always True: this adapter never performs inverter writes."""
        return True

    @property
    def last_action(self) -> ControlActionRecord | None:
        """Return the latest recorded simulation action."""
        return self._last_action

    async def async_apply_target_soc(
        self,
        target_soc_pct: int,
        reason: str,
        now: datetime,
    ) -> ControlActionRecord:
        """Record a simulated target SOC recommendation without touching hardware."""
        record = ControlActionRecord(
            timestamp=now,
            action="simulate_target_soc",
            target_soc_pct=target_soc_pct,
            simulated=True,
            reason=reason,
        )
        self._last_action = record
        _LOGGER.debug(
            "Simulation only: target SOC=%s%% (%s)",
            target_soc_pct,
            reason,
        )
        return record

    async def async_stop_charge(
        self,
        reason: str,
        now: datetime,
    ) -> ControlActionRecord:
        """Record a simulated charge stop without touching hardware."""
        record = ControlActionRecord(
            timestamp=now,
            action="simulate_stop_charge",
            target_soc_pct=None,
            simulated=True,
            reason=reason,
        )
        self._last_action = record
        _LOGGER.debug("Simulation only: stop charge (%s)", reason)
        return record
