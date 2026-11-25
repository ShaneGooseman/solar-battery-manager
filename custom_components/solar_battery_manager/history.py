"""Recorder statistics adapter for extracting historical daytime house load."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import date, datetime, time, timedelta, timezone
import logging
import math
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

from .engine.models import DaytimeLoadSample

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


def resolve_solar_window_from_sun(
    next_rising_raw: Any,
    next_setting_raw: Any,
    timezone_name: str,
) -> tuple[time | None, time | None, str | None]:
    """Derive local solar window [sunrise, sunset) from Sun entity attributes.

    Returns ``(sunrise_time, sunset_time, error_reason)``.
    """
    if not next_rising_raw or not next_setting_raw:
        return None, None, "sun_entity_missing_rising_or_setting_attributes"
    try:
        tz = ZoneInfo(timezone_name)
        rising_dt = (
            next_rising_raw
            if isinstance(next_rising_raw, datetime)
            else datetime.fromisoformat(str(next_rising_raw))
        )
        setting_dt = (
            next_setting_raw
            if isinstance(next_setting_raw, datetime)
            else datetime.fromisoformat(str(next_setting_raw))
        )
        if rising_dt.tzinfo is None or setting_dt.tzinfo is None:
            return None, None, "sun_entity_attributes_must_be_timezone_aware"
        start_t = rising_dt.astimezone(tz).time().replace(tzinfo=None, microsecond=0)
        end_t = setting_dt.astimezone(tz).time().replace(tzinfo=None, microsecond=0)
        if start_t >= end_t:
            return None, None, "sun_entity_sunrise_not_before_sunset"
        return start_t, end_t, None
    except (TypeError, ValueError):
        return None, None, "sun_entity_invalid_datetime_attributes"


def _parse_stat_start(raw_start: Any, tz: ZoneInfo) -> datetime | None:
    """Convert a Recorder statistics 'start' field to a local aware datetime."""
    if isinstance(raw_start, datetime):
        dt = raw_start if raw_start.tzinfo is not None else raw_start.replace(tzinfo=timezone.utc)
        return dt.astimezone(tz)
    if isinstance(raw_start, (int, float)) and not isinstance(raw_start, bool):
        return datetime.fromtimestamp(float(raw_start), tz=timezone.utc).astimezone(tz)
    return None


def extract_daytime_samples_from_hourly_stats(
    rows: Sequence[Mapping[str, Any]],
    *,
    solar_start: time,
    solar_end: time,
    timezone_name: str,
    end_date_exclusive: date,
    lookback_days: int,
    unit_scale_to_kwh: float = 1.0,
) -> list[DaytimeLoadSample]:
    """Aggregate hourly Recorder statistics into daily daytime load samples.

    Only hours whose local start time falls inside ``[solar_start, solar_end)``
    are summed, excluding nighttime consumption covered by the grid.
    """
    if solar_start >= solar_end:
        raise ValueError("solar_start must be earlier than solar_end.")
    if lookback_days <= 0:
        raise ValueError("lookback_days must be greater than 0.")
    if unit_scale_to_kwh <= 0 or not math.isfinite(unit_scale_to_kwh):
        raise ValueError("unit_scale_to_kwh must be finite and > 0.")

    tz = ZoneInfo(timezone_name)
    start_date_inclusive = end_date_exclusive - timedelta(days=lookback_days)

    daily_totals: dict[date, float] = defaultdict(float)
    daily_hour_counts: dict[date, int] = defaultdict(int)
    daily_invalid_hours: dict[date, int] = defaultdict(int)

    prev_sum: float | None = None
    for row in rows:
        local_dt = _parse_stat_start(row.get("start"), tz)
        if local_dt is None:
            continue

        row_sum = row.get("sum")
        raw_change = row.get("change")

        hourly_value: float | None = None
        if raw_change is not None and not isinstance(raw_change, bool) and math.isfinite(float(raw_change)):
            hourly_value = float(raw_change)
        elif (
            row_sum is not None
            and not isinstance(row_sum, bool)
            and math.isfinite(float(row_sum))
            and prev_sum is not None
        ):
            hourly_value = float(row_sum) - prev_sum

        if row_sum is not None and not isinstance(row_sum, bool) and math.isfinite(float(row_sum)):
            prev_sum = float(row_sum)

        row_date = local_dt.date()
        if row_date < start_date_inclusive or row_date >= end_date_exclusive:
            continue

        local_t = local_dt.time().replace(tzinfo=None)
        if not (solar_start <= local_t < solar_end):
            continue

        if hourly_value is None or hourly_value < 0:
            daily_invalid_hours[row_date] += 1
            continue

        daily_totals[row_date] += hourly_value * unit_scale_to_kwh
        daily_hour_counts[row_date] += 1

    expected_hours = max(
        1,
        math.ceil(
            (
                datetime.combine(end_date_exclusive, solar_end)
                - datetime.combine(end_date_exclusive, solar_start)
            ).total_seconds()
            / 3600.0
        ),
    )
    min_required_hours = max(1, math.ceil(expected_hours * 0.75))

    samples: list[DaytimeLoadSample] = []
    for offset in range(lookback_days):
        day = start_date_inclusive + timedelta(days=offset)
        valid_hours = daily_hour_counts.get(day, 0)
        invalid_hours = daily_invalid_hours.get(day, 0)
        if valid_hours == 0:
            reason = (
                "invalid_hourly_statistics"
                if invalid_hours > 0
                else "missing_hourly_statistics"
            )
            samples.append(
                DaytimeLoadSample(
                    sample_date=day,
                    kwh=None,
                    is_valid=False,
                    invalid_reason=reason,
                )
            )
        elif valid_hours < min_required_hours:
            samples.append(
                DaytimeLoadSample(
                    sample_date=day,
                    kwh=None,
                    is_valid=False,
                    invalid_reason=(
                        f"incomplete_solar_window_hours:{valid_hours}/{expected_hours}"
                    ),
                )
            )
        else:
            samples.append(
                DaytimeLoadSample(
                    sample_date=day,
                    kwh=round(daily_totals[day], 4),
                    is_valid=True,
                )
            )

    return samples


async def async_fetch_daytime_load_history(
    hass: HomeAssistant,
    *,
    entity_id: str,
    solar_start: time,
    solar_end: time,
    timezone_name: str,
    lookback_days: int,
    unit_scale_to_kwh: float = 1.0,
    now: datetime | None = None,
) -> list[DaytimeLoadSample]:
    """Query Home Assistant Core Recorder statistics for daytime house load."""
    from homeassistant.components.recorder import get_instance
    from homeassistant.components.recorder.statistics import statistics_during_period

    tz = ZoneInfo(timezone_name)
    now_local = (now or datetime.now(timezone.utc)).astimezone(tz)
    end_date_exclusive = now_local.date()

    # Fetch one extra hour before start_date to allow sum-diff fallback if needed.
    start_local = datetime.combine(
        end_date_exclusive - timedelta(days=lookback_days),
        time(0, 0),
        tzinfo=tz,
    ) - timedelta(hours=1)
    end_local = datetime.combine(end_date_exclusive, time(0, 0), tzinfo=tz)

    stats_by_id = await get_instance(hass).async_add_executor_job(
        statistics_during_period,
        hass,
        start_local.astimezone(timezone.utc),
        end_local.astimezone(timezone.utc),
        {entity_id},
        "hour",
        None,
        {"change", "sum"},
    )
    rows = stats_by_id.get(entity_id, [])
    _LOGGER.debug(
        "Fetched %d hourly recorder statistics rows for %s",
        len(rows),
        entity_id,
    )
    return extract_daytime_samples_from_hourly_stats(
        rows,
        solar_start=solar_start,
        solar_end=solar_end,
        timezone_name=timezone_name,
        end_date_exclusive=end_date_exclusive,
        lookback_days=lookback_days,
        unit_scale_to_kwh=unit_scale_to_kwh,
    )
