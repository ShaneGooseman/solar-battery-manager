"""Unit tests for control decision logic and PV forecast error calculation."""

from __future__ import annotations

from datetime import date, datetime, timedelta
import unittest
from zoneinfo import ZoneInfo

from custom_components.solar_battery_manager.engine import (
    BatteryConfig,
    DaytimeLoadSample,
    TariffScheduleConfig,
    calculate_forecast_error,
    calculate_target_soc,
    decide_program_soc_action,
    evaluate_schedule,
    plan_charge_window,
)


def _history(kwh: float = 4.0) -> list[DaytimeLoadSample]:
    start = date(2026, 11, 1)
    return [DaytimeLoadSample(start + timedelta(days=i), kwh) for i in range(5)]


class TestControlDecisionAndForecastError(unittest.TestCase):
    """Test cases for fail-safe control decisions and forecast accuracy."""

    def test_waits_at_idle_soc_before_start_time_then_applies_target(self) -> None:
        tz = ZoneInfo("Europe/Madrid")
        schedule_cfg = TariffScheduleConfig()
        cfg = BatteryConfig(usable_battery_kwh=12.0, charge_efficiency=0.90, safety_margin_soc=5.0)

        # 02:00 inside window, target=60%, current=40% -> start at 05:52 -> should wait at 20%
        now_early = datetime(2026, 11, 26, 2, 0, tzinfo=tz)
        sched_early = evaluate_schedule(now_early, schedule_cfg)
        res_early = calculate_target_soc(
            pv_forecast_kwh=10.0,
            load_samples=_history(4.0),
            config=cfg,
            current_soc_pct=40.0,
            target_night_date=sched_early.target_night_date,
        )
        plan_early = plan_charge_window(
            result=res_early,
            schedule_state=sched_early,
            schedule_config=schedule_cfg,
            charging_current_a=25.0,
        )
        soc, action, _ = decide_program_soc_action(
            result=res_early,
            schedule_state=sched_early,
            charge_plan=plan_early,
            night_idle_soc=20.0,
            real_control_enabled=True,
        )
        self.assertEqual(soc, 20)
        self.assertEqual(action, "wait_idle_soc")

        # 06:10 inside window -> should apply target 60%
        now_charge = datetime(2026, 11, 26, 6, 10, tzinfo=tz)
        sched_charge = evaluate_schedule(now_charge, schedule_cfg)
        plan_charge = plan_charge_window(
            result=res_early,
            schedule_state=sched_charge,
            schedule_config=schedule_cfg,
            charging_current_a=25.0,
        )
        soc2, action2, _ = decide_program_soc_action(
            result=res_early,
            schedule_state=sched_charge,
            charge_plan=plan_charge,
            night_idle_soc=20.0,
            real_control_enabled=True,
        )
        self.assertEqual(soc2, 60)
        self.assertEqual(action2, "apply_target_soc")

    def test_outside_window_restores_idle_soc(self) -> None:
        tz = ZoneInfo("Europe/Madrid")
        schedule_cfg = TariffScheduleConfig()
        now_day = datetime(2026, 11, 26, 10, 0, tzinfo=tz)
        sched = evaluate_schedule(now_day, schedule_cfg)
        cfg = BatteryConfig(usable_battery_kwh=12.0)
        res = calculate_target_soc(
            pv_forecast_kwh=10.0,
            load_samples=_history(4.0),
            config=cfg,
            current_soc_pct=80.0,
        )
        plan = plan_charge_window(
            result=res,
            schedule_state=sched,
            schedule_config=schedule_cfg,
            charging_current_a=25.0,
        )
        soc, action, _ = decide_program_soc_action(
            result=res,
            schedule_state=sched,
            charge_plan=plan,
            night_idle_soc=20.0,
            real_control_enabled=True,
        )
        self.assertEqual(soc, 20)
        self.assertEqual(action, "restore_idle_soc")

    def test_invalid_calculation_inside_window_refuses_charge(self) -> None:
        tz = ZoneInfo("Europe/Madrid")
        schedule_cfg = TariffScheduleConfig()
        now_night = datetime(2026, 11, 26, 3, 0, tzinfo=tz)
        sched = evaluate_schedule(now_night, schedule_cfg)
        cfg = BatteryConfig(usable_battery_kwh=12.0)
        res = calculate_target_soc(
            pv_forecast_kwh=None,
            load_samples=_history(4.0),
            config=cfg,
            current_soc_pct=30.0,
        )
        plan = plan_charge_window(
            result=res,
            schedule_state=sched,
            schedule_config=schedule_cfg,
            charging_current_a=25.0,
        )
        soc, action, _ = decide_program_soc_action(
            result=res,
            schedule_state=sched,
            charge_plan=plan,
            night_idle_soc=20.0,
            real_control_enabled=True,
        )
        self.assertIsNone(soc)
        self.assertEqual(action, "fail_safe_hold")

    def test_latched_charge_prevents_chattering_if_start_shifts_forward(self) -> None:
        tz = ZoneInfo("Europe/Madrid")
        schedule_cfg = TariffScheduleConfig()
        # 05:00 inside window, should_charge_now is False (start is 05:52),
        # but charge_latched=True must keep target_soc=60% instead of dropping to 20%.
        now_night = datetime(2026, 11, 26, 5, 0, tzinfo=tz)
        sched = evaluate_schedule(now_night, schedule_cfg)
        cfg = BatteryConfig(usable_battery_kwh=12.0, charge_efficiency=0.90, safety_margin_soc=5.0)
        res = calculate_target_soc(
            pv_forecast_kwh=10.0,
            load_samples=_history(4.0),
            config=cfg,
            current_soc_pct=40.0,
            target_night_date=sched.target_night_date,
        )
        plan = plan_charge_window(
            result=res,
            schedule_state=sched,
            schedule_config=schedule_cfg,
            charging_current_a=25.0,
        )
        self.assertFalse(plan.should_charge_now)
        soc, action, _ = decide_program_soc_action(
            result=res,
            schedule_state=sched,
            charge_plan=plan,
            night_idle_soc=20.0,
            real_control_enabled=True,
            charge_latched=True,
        )
        self.assertEqual(soc, 60)
        self.assertEqual(action, "apply_target_soc")

    def test_forecast_error_calculation(self) -> None:
        err_kwh, err_pct = calculate_forecast_error(
            forecast_kwh=10.0,
            actual_production_kwh=11.5,
        )
        self.assertAlmostEqual(err_kwh or 0.0, 1.5)
        self.assertAlmostEqual(err_pct or 0.0, 15.0)

        self.assertEqual(
            calculate_forecast_error(forecast_kwh=None, actual_production_kwh=5.0),
            (None, None),
        )


if __name__ == "__main__":
    unittest.main()
