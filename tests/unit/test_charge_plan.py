"""Unit tests for grid charge start time planning based on max current."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
import unittest
from zoneinfo import ZoneInfo

from custom_components.solar_battery_manager.engine import (
    BatteryConfig,
    DaytimeLoadSample,
    TariffScheduleConfig,
    calculate_target_soc,
    evaluate_schedule,
    plan_charge_window,
)


def _history(kwh: float = 4.0) -> list[DaytimeLoadSample]:
    start = date(2026, 11, 1)
    return [DaytimeLoadSample(start + timedelta(days=i), kwh) for i in range(5)]


class TestChargePlan(unittest.TestCase):
    """Test cases for plan_charge_window."""

    def test_calculates_start_time_from_max_current(self) -> None:
        tz = ZoneInfo("Europe/Madrid")
        schedule_cfg = TariffScheduleConfig()
        # 23:55 -> freeze active for target_night_date 2026-11-26
        now = datetime(2026, 11, 25, 23, 55, tzinfo=tz)
        sched_state = evaluate_schedule(now, schedule_cfg)

        # surplus = 6.0 -> gain = 45% -> target = 60% (with margin 5%)
        # current = 40% -> delta = 20% of 12 kWh = 2.4 kWh
        # 25 A * 51.2 V = 1.28 kW -> 2.4 / 1.28 * 60 = 112.5 -> ceil 113 min + 15 min = 128 min
        # 08:00 - 128 min = 05:52
        cfg = BatteryConfig(usable_battery_kwh=12.0, charge_efficiency=0.90, safety_margin_soc=5.0)
        res = calculate_target_soc(
            pv_forecast_kwh=10.0,
            load_samples=_history(4.0),
            config=cfg,
            current_soc_pct=40.0,
            target_night_date=sched_state.target_night_date,
        )
        plan = plan_charge_window(
            result=res,
            schedule_state=sched_state,
            schedule_config=schedule_cfg,
            charging_current_a=25.0,
            nominal_voltage_v=51.2,
            buffer_minutes=15,
        )
        self.assertTrue(plan.is_valid)
        self.assertAlmostEqual(plan.charging_power_kw or 0.0, 1.28)
        self.assertEqual(plan.estimated_duration_minutes, 128)
        self.assertEqual(plan.recommended_start_at, datetime(2026, 11, 26, 5, 52, tzinfo=tz))
        self.assertTrue(plan.can_reach_target_in_window)
        self.assertFalse(plan.should_charge_now)

    def test_should_charge_now_turns_true_when_start_time_reached(self) -> None:
        tz = ZoneInfo("Europe/Madrid")
        schedule_cfg = TariffScheduleConfig()
        now = datetime(2026, 11, 26, 6, 0, tzinfo=tz)
        sched_state = evaluate_schedule(now, schedule_cfg)
        cfg = BatteryConfig(usable_battery_kwh=12.0, charge_efficiency=0.90, safety_margin_soc=5.0)
        res = calculate_target_soc(
            pv_forecast_kwh=10.0,
            load_samples=_history(4.0),
            config=cfg,
            current_soc_pct=40.0,
            target_night_date=sched_state.target_night_date,
        )
        plan = plan_charge_window(
            result=res,
            schedule_state=sched_state,
            schedule_config=schedule_cfg,
            charging_current_a=25.0,
        )
        self.assertTrue(plan.is_valid)
        self.assertTrue(plan.should_charge_now)

    def test_duration_exceeding_window_clamps_start_and_flags_warning(self) -> None:
        tz = ZoneInfo("Europe/Madrid")
        schedule_cfg = TariffScheduleConfig()
        now = datetime(2026, 11, 26, 1, 0, tzinfo=tz)
        sched_state = evaluate_schedule(now, schedule_cfg)
        cfg = BatteryConfig(usable_battery_kwh=12.0, charge_efficiency=0.90, safety_margin_soc=5.0)
        # pv = 0 -> target = 100%, current = 10% -> delta = 10.8 kWh; at 10 A (0.512 kW) > 21h
        res = calculate_target_soc(
            pv_forecast_kwh=0.0,
            load_samples=_history(4.0),
            config=cfg,
            current_soc_pct=10.0,
            target_night_date=sched_state.target_night_date,
        )
        plan = plan_charge_window(
            result=res,
            schedule_state=sched_state,
            schedule_config=schedule_cfg,
            charging_current_a=10.0,
        )
        self.assertTrue(plan.is_valid)
        self.assertFalse(plan.can_reach_target_in_window)
        self.assertEqual(plan.recommended_start_at, datetime(2026, 11, 26, 0, 0, tzinfo=tz))
        self.assertTrue(plan.should_charge_now)

    def test_already_at_target_soc_needs_zero_minutes(self) -> None:
        tz = ZoneInfo("Europe/Madrid")
        schedule_cfg = TariffScheduleConfig()
        now = datetime(2026, 11, 26, 2, 0, tzinfo=tz)
        sched_state = evaluate_schedule(now, schedule_cfg)
        cfg = BatteryConfig(usable_battery_kwh=12.0)
        res = calculate_target_soc(
            pv_forecast_kwh=10.0,
            load_samples=_history(4.0),
            config=cfg,
            current_soc_pct=80.0,
            target_night_date=sched_state.target_night_date,
        )
        plan = plan_charge_window(
            result=res,
            schedule_state=sched_state,
            schedule_config=schedule_cfg,
            charging_current_a=25.0,
        )
        self.assertTrue(plan.is_valid)
        self.assertEqual(plan.estimated_duration_minutes, 0)
        self.assertFalse(plan.should_charge_now)

    def test_missing_or_zero_current_fails_safely(self) -> None:
        tz = ZoneInfo("Europe/Madrid")
        schedule_cfg = TariffScheduleConfig()
        now = datetime(2026, 11, 26, 2, 0, tzinfo=tz)
        sched_state = evaluate_schedule(now, schedule_cfg)
        cfg = BatteryConfig(usable_battery_kwh=12.0)
        res = calculate_target_soc(
            pv_forecast_kwh=10.0,
            load_samples=_history(4.0),
            config=cfg,
            current_soc_pct=40.0,
        )
        for bad_current in (None, 0.0, -5.0):
            plan = plan_charge_window(
                result=res,
                schedule_state=sched_state,
                schedule_config=schedule_cfg,
                charging_current_a=bad_current,
            )
            self.assertFalse(plan.is_valid)
            self.assertIsNone(plan.recommended_start_at)
            self.assertFalse(plan.should_charge_now)


if __name__ == "__main__":
    unittest.main()
