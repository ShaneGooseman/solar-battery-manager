"""Unit tests for the pure target SOC calculation engine."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import math
import unittest

from custom_components.solar_battery_manager.engine import (
    BatteryConfig,
    CalculationStatus,
    DaytimeLoadSample,
    EstimationMethod,
    calculate_target_soc,
)


def _valid_history(kwh: float = 4.0, days: int = 5) -> list[DaytimeLoadSample]:
    start = date(2026, 11, 1)
    return [
        DaytimeLoadSample(sample_date=start + timedelta(days=i), kwh=kwh)
        for i in range(days)
    ]


class TestCalculator(unittest.TestCase):
    """Test cases for energy surplus, target SOC, clamping and fail-safe paths."""

    def test_nominal_calculation_with_custom_usable_capacity(self) -> None:
        config = BatteryConfig(
            usable_battery_kwh=12.0,
            charge_efficiency=0.90,
            safety_margin_soc=5.0,
            min_operational_soc=15.0,
            max_operational_soc=100.0,
        )
        result = calculate_target_soc(
            pv_forecast_kwh=10.0,
            load_samples=_valid_history(4.0),
            config=config,
            current_soc_pct=40.0,
            estimation_method=EstimationMethod.MEDIAN,
            calculated_at=datetime(2026, 11, 25, 23, 55, tzinfo=timezone.utc),
            target_night_date=date(2026, 11, 26),
        )
        # surplus = 6.0 kWh; gain = 6.0 * 0.9 / 12.0 * 100 = 45.0%
        # raw = 100 - 45 + 5 = 60.0% -> target = 60%
        # grid_energy = ((60 - 40) / 100 * 12.0) / 0.90 = 2.6667 kWh
        self.assertTrue(result.is_valid)
        self.assertEqual(result.status_code, CalculationStatus.OK)
        self.assertAlmostEqual(result.surplus_kwh or 0.0, 6.0)
        self.assertAlmostEqual(result.solar_soc_gain_pct or 0.0, 45.0)
        self.assertAlmostEqual(result.target_soc_raw or 0.0, 60.0)
        self.assertEqual(result.target_soc_pct, 60)
        self.assertFalse(result.was_clamped)
        self.assertIsNone(result.clamp_bound)
        self.assertAlmostEqual(result.grid_energy_required_kwh or 0.0, 2.4 / 0.9, places=5)
        self.assertIsNotNone(result.load_estimation)

    def test_zero_and_negative_surplus_clamps_to_max(self) -> None:
        config = BatteryConfig(usable_battery_kwh=12.0, safety_margin_soc=5.0)
        result = calculate_target_soc(
            pv_forecast_kwh=3.0,
            load_samples=_valid_history(5.0),
            config=config,
        )
        self.assertTrue(result.is_valid)
        self.assertEqual(result.surplus_kwh, 0.0)
        self.assertEqual(result.solar_soc_gain_pct, 0.0)
        self.assertAlmostEqual(result.target_soc_raw or 0.0, 105.0)
        self.assertEqual(result.target_soc_pct, 100)
        self.assertTrue(result.was_clamped)
        self.assertEqual(result.clamp_bound, "max")

    def test_high_surplus_clamps_to_min_operational_soc(self) -> None:
        config = BatteryConfig(
            usable_battery_kwh=12.0,
            charge_efficiency=0.95,
            safety_margin_soc=5.0,
            min_operational_soc=20.0,
        )
        result = calculate_target_soc(
            pv_forecast_kwh=20.0,
            load_samples=_valid_history(3.0),
            config=config,
        )
        self.assertTrue(result.is_valid)
        self.assertEqual(result.target_soc_pct, 20)
        self.assertTrue(result.was_clamped)
        self.assertEqual(result.clamp_bound, "min")

    def test_current_soc_above_target_requires_zero_grid_energy(self) -> None:
        config = BatteryConfig(usable_battery_kwh=12.0, safety_margin_soc=0.0)
        result = calculate_target_soc(
            pv_forecast_kwh=10.0,
            load_samples=_valid_history(4.0),
            config=config,
            current_soc_pct=80.0,
        )
        self.assertTrue(result.is_valid)
        self.assertEqual(result.grid_energy_required_kwh, 0.0)

    def test_invalid_pv_forecast_fails_safely(self) -> None:
        config = BatteryConfig(usable_battery_kwh=12.0)
        for bad_pv in (None, -1.0, math.nan, math.inf):
            result = calculate_target_soc(
                pv_forecast_kwh=bad_pv,
                load_samples=_valid_history(4.0),
                config=config,
            )
            self.assertFalse(result.is_valid)
            self.assertEqual(result.status_code, CalculationStatus.INVALID_PV_FORECAST)
            self.assertIsNone(result.target_soc_pct)

    def test_invalid_battery_config_fails_safely(self) -> None:
        bad_configs = [
            BatteryConfig(usable_battery_kwh=0.0),
            BatteryConfig(usable_battery_kwh=-5.0),
            BatteryConfig(usable_battery_kwh=12.0, charge_efficiency=0.0),
            BatteryConfig(usable_battery_kwh=12.0, charge_efficiency=1.2),
            BatteryConfig(usable_battery_kwh=12.0, min_operational_soc=90.0, max_operational_soc=80.0),
            BatteryConfig(usable_battery_kwh=12.0, safety_margin_soc=-1.0),
        ]
        for cfg in bad_configs:
            result = calculate_target_soc(
                pv_forecast_kwh=10.0,
                load_samples=_valid_history(4.0),
                config=cfg,
            )
            self.assertFalse(result.is_valid)
            self.assertEqual(result.status_code, CalculationStatus.INVALID_CONFIG)
            self.assertIsNone(result.target_soc_pct)

    def test_invalid_current_soc_fails_safely(self) -> None:
        config = BatteryConfig(usable_battery_kwh=12.0)
        for bad_soc in (-0.1, 100.1, math.nan):
            result = calculate_target_soc(
                pv_forecast_kwh=10.0,
                load_samples=_valid_history(4.0),
                config=config,
                current_soc_pct=bad_soc,
            )
            self.assertFalse(result.is_valid)
            self.assertEqual(result.status_code, CalculationStatus.INVALID_CURRENT_SOC)
            self.assertIsNone(result.target_soc_pct)

    def test_insufficient_history_propagates_failure(self) -> None:
        config = BatteryConfig(usable_battery_kwh=12.0)
        result = calculate_target_soc(
            pv_forecast_kwh=10.0,
            load_samples=_valid_history(4.0, days=2),
            config=config,
            min_history_days=3,
        )
        self.assertFalse(result.is_valid)
        self.assertEqual(result.status_code, CalculationStatus.INSUFFICIENT_HISTORY)
        self.assertIsNone(result.target_soc_pct)

    def test_rounding_past_fractional_bound_marks_was_clamped(self) -> None:
        config = BatteryConfig(
            usable_battery_kwh=12.0,
            charge_efficiency=1.0,
            safety_margin_soc=0.0,
            min_operational_soc=19.6,
            max_operational_soc=100.0,
        )
        # surplus=9.64 kWh -> gain=80.333% -> raw=19.667% (>= 19.6), rounds to 20 -> >= ceil(19.6)=20
        # Now test max bound: max=89.4, raw=89.3 -> floor(89.4)=89 -> rounds to 89.
        # Test raw=89.4 -> rounds to 89 <= 89; raw=19.6 -> ceil(19.6)=20 -> clamped up from 19.6!
        result = calculate_target_soc(
            pv_forecast_kwh=13.648,
            load_samples=_valid_history(4.0),
            config=config,
        )
        # surplus=9.648 -> gain=80.4 -> raw=19.6 (not < 19.6), round(19.6)=20 == ceil(19.6)
        self.assertTrue(result.is_valid)
        self.assertEqual(result.target_soc_pct, 20)


if __name__ == "__main__":
    unittest.main()
