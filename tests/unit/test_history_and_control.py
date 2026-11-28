"""Unit tests for hourly recorder aggregation and read-only simulation controller."""

from __future__ import annotations

from collections.abc import Coroutine
from datetime import date, datetime, time, timezone
from typing import Any, TypeVar
import unittest
from zoneinfo import ZoneInfo

from custom_components.solar_battery_manager.control import ReadOnlySimulationController
from custom_components.solar_battery_manager.history import (
    extract_daytime_samples_from_hourly_stats,
    resolve_solar_window_from_sun,
)

_T = TypeVar("_T")


def _run_pure_coro(coro: Coroutine[Any, Any, _T]) -> _T:
    """Drive a non-blocking coroutine to completion without spawning an event loop."""
    try:
        coro.send(None)
    except StopIteration as exc:
        return exc.value  # type: ignore[return-value]
    finally:
        coro.close()
    raise AssertionError("Expected coroutine to complete without yielding.")


class TestHistoryAggregation(unittest.TestCase):
    """Test cases for extracting daytime load from hourly recorder stats."""

    def test_aggregates_only_solar_hours_and_ignores_night(self) -> None:
        tz = ZoneInfo("Europe/Madrid")
        # Day 2026-11-24: solar window 08:00-12:00 (4h) -> 3h valid (75%) passes
        rows = [
            {"start": datetime(2026, 11, 24, 2, 0, tzinfo=tz), "change": 3.0},
            {"start": datetime(2026, 11, 24, 8, 0, tzinfo=tz), "change": 0.5},
            {"start": datetime(2026, 11, 24, 9, 0, tzinfo=tz), "change": 1.2},
            {"start": datetime(2026, 11, 24, 10, 0, tzinfo=tz), "change": 0.8},
            {"start": datetime(2026, 11, 24, 22, 0, tzinfo=tz), "change": 2.5},
        ]
        samples = extract_daytime_samples_from_hourly_stats(
            rows,
            solar_start=time(8, 0),
            solar_end=time(12, 0),
            timezone_name="Europe/Madrid",
            end_date_exclusive=date(2026, 11, 25),
            lookback_days=2,
        )
        self.assertEqual(len(samples), 2)
        self.assertFalse(samples[0].is_valid)
        self.assertEqual(samples[0].invalid_reason, "missing_hourly_statistics")
        self.assertTrue(samples[1].is_valid)
        self.assertAlmostEqual(samples[1].kwh or 0.0, 2.5)

    def test_rejects_partial_day_below_completeness_threshold(self) -> None:
        tz = ZoneInfo("Europe/Madrid")
        # Solar window 08:00-18:00 (10h -> requires >= 8h). Only 2h present -> rejected.
        rows = [
            {"start": datetime(2026, 11, 24, 9, 0, tzinfo=tz), "change": 1.0},
            {"start": datetime(2026, 11, 24, 10, 0, tzinfo=tz), "change": 1.0},
        ]
        samples = extract_daytime_samples_from_hourly_stats(
            rows,
            solar_start=time(8, 0),
            solar_end=time(18, 0),
            timezone_name="Europe/Madrid",
            end_date_exclusive=date(2026, 11, 25),
            lookback_days=1,
        )
        self.assertEqual(len(samples), 1)
        self.assertFalse(samples[0].is_valid)
        self.assertTrue(
            (samples[0].invalid_reason or "").startswith("incomplete_solar_window_hours:")
        )

    def test_converts_wh_to_kwh_and_falls_back_to_sum_diff(self) -> None:
        tz = ZoneInfo("Europe/Madrid")
        rows = [
            {"start": datetime(2026, 11, 24, 7, 0, tzinfo=tz), "sum": 9000.0},
            {"start": datetime(2026, 11, 24, 8, 0, tzinfo=tz), "sum": 10000.0},
            {"start": datetime(2026, 11, 24, 9, 0, tzinfo=tz), "sum": 11500.0},
        ]
        samples = extract_daytime_samples_from_hourly_stats(
            rows,
            solar_start=time(8, 0),
            solar_end=time(10, 0),
            timezone_name="Europe/Madrid",
            end_date_exclusive=date(2026, 11, 25),
            lookback_days=1,
            unit_scale_to_kwh=0.001,
        )
        self.assertEqual(len(samples), 1)
        self.assertTrue(samples[0].is_valid)
        self.assertAlmostEqual(samples[0].kwh or 0.0, 2.5)


class TestReadOnlySimulationController(unittest.TestCase):
    """Test cases for read-only simulation controller."""

    def test_controller_is_always_simulation_and_records_actions(self) -> None:
        controller = ReadOnlySimulationController()
        self.assertTrue(controller.is_simulation)
        now = datetime(2026, 11, 25, 1, 0, tzinfo=timezone.utc)
        record = _run_pure_coro(
            controller.async_apply_program_soc(
                action="simulate_target_soc",
                target_soc_pct=65,
                reason="Simulated overnight target",
                now=now,
            )
        )
        self.assertTrue(record.simulated)
        self.assertEqual(record.target_soc_pct, 65)
        self.assertEqual(controller.last_action, record)


class TestSunSolarWindow(unittest.TestCase):
    """Test cases for deriving solar window from Sun entity attributes."""

    def test_extracts_local_sunrise_and_sunset(self) -> None:
        # 06:50 UTC = 07:50 CET; 16:45 UTC = 17:45 CET
        start, end, err = resolve_solar_window_from_sun(
            "2026-11-26T06:50:00+00:00",
            "2026-11-25T16:45:00+00:00",
            "Europe/Madrid",
        )
        self.assertIsNone(err)
        self.assertEqual(start, time(7, 50))
        self.assertEqual(end, time(17, 45))

    def test_returns_error_when_sun_attributes_missing_or_invalid(self) -> None:
        start, end, err = resolve_solar_window_from_sun(
            None,
            "invalid",
            "Europe/Madrid",
        )
        self.assertIsNone(start)
        self.assertIsNone(end)
        self.assertIsNotNone(err)

    def test_accepts_pre_resolved_tzinfo_object(self) -> None:
        tz = ZoneInfo("Europe/Madrid")
        start, end, err = resolve_solar_window_from_sun(
            "2026-11-26T06:50:00+00:00",
            "2026-11-25T16:45:00+00:00",
            tz,
        )
        self.assertIsNone(err)
        self.assertEqual(start, time(7, 50))
        self.assertEqual(end, time(17, 45))

        rows = [
            {"start": datetime(2026, 11, 24, 8, 0, tzinfo=tz), "change": 1.0},
            {"start": datetime(2026, 11, 24, 9, 0, tzinfo=tz), "change": 1.5},
        ]
        samples = extract_daytime_samples_from_hourly_stats(
            rows,
            solar_start=time(8, 0),
            solar_end=time(10, 0),
            timezone_name=tz,
            end_date_exclusive=date(2026, 11, 25),
            lookback_days=1,
        )
        self.assertEqual(len(samples), 1)
        self.assertTrue(samples[0].is_valid)
        self.assertAlmostEqual(samples[0].kwh or 0.0, 2.5)


if __name__ == "__main__":
    unittest.main()
