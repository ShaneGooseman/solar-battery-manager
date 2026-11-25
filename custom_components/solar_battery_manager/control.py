"""Interchangeable inverter control adapters (simulation and opt-in Deye SOC)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
import logging
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ControlActionRecord:
    """Audit record of a simulated or real control decision."""

    timestamp: datetime
    action: str
    target_soc_pct: int | None
    simulated: bool
    reason: str
    verified: bool | None = None
    state_changed: bool = False


class InverterController(Protocol):
    """Protocol for inverter control adapters."""

    @property
    def is_simulation(self) -> bool:
        """Return True when running in read-only simulation mode."""

    @property
    def last_action(self) -> ControlActionRecord | None:
        """Return the latest recorded control action."""

    async def async_apply_program_soc(
        self,
        *,
        action: str,
        target_soc_pct: int | None,
        reason: str,
        now: datetime,
    ) -> ControlActionRecord:
        """Apply or simulate a Program SOC decision."""


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

    async def async_apply_program_soc(
        self,
        *,
        action: str,
        target_soc_pct: int | None,
        reason: str,
        now: datetime,
    ) -> ControlActionRecord:
        """Record a simulated target SOC decision without touching hardware."""
        record = ControlActionRecord(
            timestamp=now,
            action=action,
            target_soc_pct=target_soc_pct,
            simulated=True,
            reason=reason,
            verified=None,
        )
        self._last_action = record
        _LOGGER.debug("Simulation [%s]: target SOC=%s%% (%s)", action, target_soc_pct, reason)
        return record


class DeyeProgramSocController:
    """Opt-in Deye controller that updates only the Program 1 SOC number entity."""

    def __init__(self, hass: HomeAssistant, entity_id: str) -> None:
        self._hass = hass
        self._entity_id = entity_id
        self._last_action: ControlActionRecord | None = None

    @property
    def is_simulation(self) -> bool:
        """False: real control is enabled for this adapter."""
        return False

    @property
    def last_action(self) -> ControlActionRecord | None:
        """Return the latest recorded control action."""
        return self._last_action

    async def async_apply_program_soc(
        self,
        *,
        action: str,
        target_soc_pct: int | None,
        reason: str,
        now: datetime,
    ) -> ControlActionRecord:
        """Write target SOC to the configured Deye Program SOC entity and verify."""
        if target_soc_pct is None:
            record = ControlActionRecord(
                timestamp=now,
                action=action,
                target_soc_pct=None,
                simulated=False,
                reason=reason,
                verified=None,
            )
            self._last_action = record
            return record

        state_obj = self._hass.states.get(self._entity_id)
        if state_obj is None or state_obj.state in ("unknown", "unavailable", "", None):
            record = ControlActionRecord(
                timestamp=now,
                action="write_skipped_unavailable",
                target_soc_pct=target_soc_pct,
                simulated=False,
                reason=f"Target entity '{self._entity_id}' is unavailable.",
                verified=False,
            )
            self._last_action = record
            _LOGGER.warning("%s", record.reason)
            return record

        try:
            current_val = float(state_obj.state)
        except (TypeError, ValueError):
            current_val = None

        if current_val is not None and abs(current_val - float(target_soc_pct)) < 0.5:
            record = ControlActionRecord(
                timestamp=now,
                action=action,
                target_soc_pct=target_soc_pct,
                simulated=False,
                reason=f"{reason} (already at {target_soc_pct}%)",
                verified=True,
                state_changed=False,
            )
            self._last_action = record
            return record

        verified = False
        observed_state: str | None = None
        for attempt in range(2):
            await self._hass.services.async_call(
                "number",
                "set_value",
                {"entity_id": self._entity_id, "value": target_soc_pct},
                blocking=True,
            )
            for _ in range(5):
                await asyncio.sleep(1.0)
                verified_state = self._hass.states.get(self._entity_id)
                observed_state = verified_state.state if verified_state else None
                if verified_state is not None and verified_state.state not in ("unknown", "unavailable"):
                    try:
                        if abs(float(verified_state.state) - float(target_soc_pct)) < 0.5:
                            verified = True
                            break
                    except (TypeError, ValueError):
                        pass
            if verified:
                break
            _LOGGER.warning(
                "Attempt %d to verify %s=%s%% failed (observed=%s)",
                attempt + 1,
                self._entity_id,
                target_soc_pct,
                observed_state,
            )

        record = ControlActionRecord(
            timestamp=now,
            action=action if verified else "write_verification_failed",
            target_soc_pct=target_soc_pct,
            simulated=False,
            reason=(
                reason
                if verified
                else f"Write to '{self._entity_id}' could not be verified after retry (observed={observed_state})."
            ),
            verified=verified,
            state_changed=True,
        )
        self._last_action = record
        if not verified:
            _LOGGER.warning("%s", record.reason)
        else:
            _LOGGER.info("Deye %s updated to %s%% (%s)", self._entity_id, target_soc_pct, action)
        return record
