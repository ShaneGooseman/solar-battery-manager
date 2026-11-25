"""Unit tests for economic tariff window and freeze schedule evaluation."""

from __future__ import annotations

from datetime import date, datetime, time, timezone
import unittest
from zoneinfo import ZoneInfo

from custom_components.solar_battery_manager.engine import (
    TariffScheduleConfig,
    evaluate_schedule,
)


class TestSchedule(unittest.TestCase):
    """Test cases for tariff windows, midnight crossing and DST transitions."""

    def test_standard_window_before_freeze(self) -> None:
        tz = ZoneInfo("Europe/Madrid")
        schedule = TariffScheduleConfig()
        state = evaluate_schedule(datetime(2026, 11, 25, 20, 0, tzinfo=tz), schedule)
        self.assertFalse(state.in_tariff_window)
        self.assertFalse(state.is_freeze_active)
        self.assertEqual(state.target_night_date, date(2026, 11, 26))

    def test_standard_window_after_freeze_before_midnight(self) -> None:
        tz = ZoneInfo("Europe/Madrid")
        schedule = TariffScheduleConfig()
        state = evaluate_schedule(datetime(2026, 11, 25, 23, 56, tzinfo=tz), schedule)
        self.assertFalse(state.in_tariff_window)
        self.assertTrue(state.is_freeze_active)
        self.assertEqual(state.target_night_date, date(2026, 11, 26))

    def test_standard_window_inside_night_tariff(self) -> None:
        tz = ZoneInfo("Europe/Madrid")
        schedule = TariffScheduleConfig()
        state = evaluate_schedule(datetime(2026, 11, 26, 3, 30, tzinfo=tz), schedule)
        self.assertTrue(state.in_tariff_window)
        self.assertTrue(state.is_freeze_active)
        self.assertEqual(state.target_night_date, date(2026, 11, 26))

    def test_standard_window_ends_at_0800_exclusive(self) -> None:
        tz = ZoneInfo("Europe/Madrid")
        schedule = TariffScheduleConfig()
        state = evaluate_schedule(datetime(2026, 11, 26, 8, 0, tzinfo=tz), schedule)
        self.assertFalse(state.in_tariff_window)
        self.assertFalse(state.is_freeze_active)
        self.assertEqual(state.target_night_date, date(2026, 11, 27))

    def test_overnight_crossing_window(self) -> None:
        tz = ZoneInfo("Europe/Madrid")
        schedule = TariffScheduleConfig(
            tariff_start=time(23, 0),
            tariff_end=time(7, 0),
            freeze_time=time(22, 55),
        )
        pre = evaluate_schedule(datetime(2026, 11, 25, 22, 56, tzinfo=tz), schedule)
        self.assertFalse(pre.in_tariff_window)
        self.assertTrue(pre.is_freeze_active)
        self.assertEqual(pre.target_night_date, date(2026, 11, 26))

        late = evaluate_schedule(datetime(2026, 11, 25, 23, 30, tzinfo=tz), schedule)
        self.assertTrue(late.in_tariff_window)
        self.assertTrue(late.is_freeze_active)
        self.assertEqual(late.target_night_date, date(2026, 11, 26))

        early = evaluate_schedule(datetime(2026, 11, 26, 5, 0, tzinfo=tz), schedule)
        self.assertTrue(early.in_tariff_window)
        self.assertTrue(early.is_freeze_active)
        self.assertEqual(early.target_night_date, date(2026, 11, 26))

    def test_utc_input_converts_to_local_timezone_across_dst(self) -> None:
        # In Europe/Madrid (UTC+1 in winter), 23:00 UTC is 00:00 local next day.
        schedule = TariffScheduleConfig(timezone="Europe/Madrid")
        utc_dt = datetime(2026, 11, 25, 23, 0, tzinfo=timezone.utc)
        state = evaluate_schedule(utc_dt, schedule)
        self.assertTrue(state.in_tariff_window)
        self.assertEqual(state.now_local.hour, 0)
        self.assertEqual(state.target_night_date, date(2026, 11, 26))

    def test_naive_datetime_rejected(self) -> None:
        schedule = TariffScheduleConfig()
        with self.assertRaises(ValueError):
            evaluate_schedule(datetime(2026, 11, 25, 12, 0), schedule)


if __name__ == "__main__":
    unittest.main()
