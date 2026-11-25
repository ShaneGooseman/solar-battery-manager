"""Unit tests for the pure daytime load estimator."""

from __future__ import annotations

from datetime import date, timedelta
import math
import unittest

from custom_components.solar_battery_manager.engine import (
    CalculationStatus,
    DaytimeLoadSample,
    EstimationMethod,
    estimate_daytime_load,
)


def _sample_days(values: list[float], start: date = date(2026, 11, 1)) -> list[DaytimeLoadSample]:
    return [
        DaytimeLoadSample(sample_date=start + timedelta(days=idx), kwh=val)
        for idx, val in enumerate(values)
    ]


class TestDaytimeLoadEstimator(unittest.TestCase):
    """Test cases for daytime load estimation and traceability."""

    def test_median_ignores_outlier_spike(self) -> None:
        samples = _sample_days([4.0, 4.2, 4.1, 15.0, 4.3])
        result = estimate_daytime_load(
            samples,
            method=EstimationMethod.MEDIAN,
            lookback_days=14,
            min_history_days=3,
        )
        self.assertTrue(result.is_valid)
        self.assertEqual(result.status_code, CalculationStatus.OK)
        self.assertAlmostEqual(result.estimated_kwh or 0.0, 4.2)
        self.assertEqual(len(result.samples_used), 5)
        self.assertEqual(len(result.samples_discarded), 0)

    def test_mean_calculation(self) -> None:
        samples = _sample_days([3.0, 4.0, 5.0])
        result = estimate_daytime_load(
            samples,
            method=EstimationMethod.MEAN,
            lookback_days=7,
            min_history_days=3,
        )
        self.assertTrue(result.is_valid)
        self.assertAlmostEqual(result.estimated_kwh or 0.0, 4.0)

    def test_insufficient_history_fails_safely(self) -> None:
        samples = _sample_days([4.0, 4.5])
        result = estimate_daytime_load(samples, min_history_days=3)
        self.assertFalse(result.is_valid)
        self.assertEqual(result.status_code, CalculationStatus.INSUFFICIENT_HISTORY)
        self.assertIsNone(result.estimated_kwh)

    def test_filters_invalid_negative_nan_and_future_samples_with_trace(self) -> None:
        ref = date(2026, 11, 10)
        samples = [
            DaytimeLoadSample(date(2026, 11, 7), 4.0),
            DaytimeLoadSample(date(2026, 11, 8), 5.0),
            DaytimeLoadSample(date(2026, 11, 9), 6.0),
            DaytimeLoadSample(date(2026, 11, 10), None, is_valid=False, invalid_reason="sensor_unavailable"),
            DaytimeLoadSample(date(2026, 11, 6), -1.2),
            DaytimeLoadSample(date(2026, 11, 5), math.nan),
            DaytimeLoadSample(date(2026, 11, 11), 3.5),
        ]
        result = estimate_daytime_load(
            samples,
            method=EstimationMethod.MEDIAN,
            min_history_days=3,
            reference_date=ref,
        )
        self.assertTrue(result.is_valid)
        self.assertAlmostEqual(result.estimated_kwh or 0.0, 5.0)
        self.assertEqual(len(result.samples_used), 3)
        self.assertEqual(len(result.samples_discarded), 4)
        reasons = {d.reason for d in result.samples_discarded}
        self.assertIn("sensor_unavailable", reasons)
        self.assertIn("negative_kwh", reasons)
        self.assertIn("non_finite_or_missing_kwh", reasons)
        self.assertIn("future_sample_after_reference_date", reasons)

    def test_lookback_selects_most_recent_days(self) -> None:
        samples = _sample_days([10.0, 10.0, 10.0, 2.0, 3.0, 4.0])
        result = estimate_daytime_load(
            samples,
            method=EstimationMethod.MEAN,
            lookback_days=3,
            min_history_days=3,
        )
        self.assertTrue(result.is_valid)
        self.assertAlmostEqual(result.estimated_kwh or 0.0, 3.0)
        self.assertEqual(result.samples_used[0].sample_date, date(2026, 11, 6))

    def test_duplicate_dates_keep_latest_and_record_discarded(self) -> None:
        samples = [
            DaytimeLoadSample(date(2026, 11, 1), 3.0),
            DaytimeLoadSample(date(2026, 11, 1), 4.0),
            DaytimeLoadSample(date(2026, 11, 2), 5.0),
            DaytimeLoadSample(date(2026, 11, 3), 6.0),
        ]
        result = estimate_daytime_load(samples, method=EstimationMethod.MEAN, min_history_days=3)
        self.assertTrue(result.is_valid)
        self.assertAlmostEqual(result.estimated_kwh or 0.0, 5.0)
        self.assertEqual(len(result.samples_discarded), 1)
        self.assertEqual(result.samples_discarded[0].reason, "duplicate_date_superseded")


if __name__ == "__main__":
    unittest.main()
