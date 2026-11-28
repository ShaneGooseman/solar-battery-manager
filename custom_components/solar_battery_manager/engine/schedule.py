"""Pure schedule evaluation for economic tariff windows and pre-midnight freeze."""

from __future__ import annotations

from datetime import datetime, time, timedelta, tzinfo
from zoneinfo import ZoneInfo

from .models import ScheduleState, TariffScheduleConfig


def is_within_solar_window(
    now_local: datetime,
    solar_start: time,
    solar_end: time,
) -> bool:
    """Return True when local time falls inside [solar_start, solar_end)."""
    local_t = now_local.time().replace(tzinfo=None)
    return solar_start <= local_t < solar_end


def evaluate_schedule(
    now: datetime,
    schedule: TariffScheduleConfig,
) -> ScheduleState:
    """Evaluate whether the current time is inside the tariff window or freeze period.

    ``target_night_date`` identifies the calendar date on which the active or next
    economic window ends (e.g. 08:00 of the morning after a 23:55 freeze).
    """
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be a timezone-aware datetime.")

    errors = schedule.validate()
    if errors:
        raise ValueError(" ".join(errors))

    tz = (
        schedule.timezone
        if isinstance(schedule.timezone, tzinfo)
        else ZoneInfo(schedule.timezone)
    )
    now_local = now.astimezone(tz)
    local_date = now_local.date()
    local_time = now_local.time().replace(tzinfo=None)

    start = schedule.tariff_start
    end = schedule.tariff_end
    freeze = schedule.freeze_time

    if start < end:
        in_tariff_window = start <= local_time < end
        if freeze > end:
            # Standard case: e.g. window 00:00-08:00, freeze at 23:55 previous day.
            if in_tariff_window:
                is_freeze_active = True
                target_night_date = local_date
            elif local_time >= freeze:
                is_freeze_active = True
                target_night_date = local_date + timedelta(days=1)
            else:
                is_freeze_active = False
                target_night_date = local_date + timedelta(days=1)
        else:
            # Same-day pre-window freeze: e.g. freeze 00:50, window 01:00-08:00.
            if in_tariff_window:
                is_freeze_active = True
                target_night_date = local_date
            elif freeze <= local_time < start:
                is_freeze_active = True
                target_night_date = local_date
            elif local_time < freeze:
                is_freeze_active = False
                target_night_date = local_date
            else:
                is_freeze_active = False
                target_night_date = local_date + timedelta(days=1)
    else:
        # Overnight window crossing midnight: e.g. 23:00-07:00, freeze at 22:55.
        if local_time >= start:
            in_tariff_window = True
            is_freeze_active = True
            target_night_date = local_date + timedelta(days=1)
        elif local_time < end:
            in_tariff_window = True
            is_freeze_active = True
            target_night_date = local_date
        elif freeze <= local_time < start:
            in_tariff_window = False
            is_freeze_active = True
            target_night_date = local_date + timedelta(days=1)
        else:
            in_tariff_window = False
            is_freeze_active = False
            target_night_date = local_date + timedelta(days=1)

    return ScheduleState(
        now_local=now_local,
        in_tariff_window=in_tariff_window,
        is_freeze_active=is_freeze_active,
        target_night_date=target_night_date,
    )
