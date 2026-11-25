"""Pure daytime house load estimation from historical solar-window samples."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
import math
import statistics

from .models import (
    CalculationStatus,
    DaytimeLoadSample,
    DiscardedSample,
    EstimationMethod,
    LoadEstimationResult,
)


def estimate_daytime_load(
    samples: Sequence[DaytimeLoadSample],
    *,
    method: EstimationMethod = EstimationMethod.MEDIAN,
    lookback_days: int = 14,
    min_history_days: int = 3,
    reference_date: date | None = None,
) -> LoadEstimationResult:
    """Estimate tomorrow's daytime house load from historical solar-window samples.

    Samples are validated, deduplicated by date (keeping the latest valid entry),
    ordered from newest to oldest, and capped at ``lookback_days``.
    """
    if lookback_days <= 0:
        return LoadEstimationResult(
            is_valid=False,
            status_code=CalculationStatus.INVALID_CONFIG,
            reason="lookback_days must be greater than 0.",
            estimated_kwh=None,
            method=method,
            samples_used=(),
            samples_discarded=(),
        )

    if min_history_days <= 0 or min_history_days > lookback_days:
        return LoadEstimationResult(
            is_valid=False,
            status_code=CalculationStatus.INVALID_CONFIG,
            reason="min_history_days must be between 1 and lookback_days.",
            estimated_kwh=None,
            method=method,
            samples_used=(),
            samples_discarded=(),
        )

    valid_by_date: dict[date, DaytimeLoadSample] = {}
    discarded: list[DiscardedSample] = []

    for sample in samples:
        if reference_date is not None and sample.sample_date > reference_date:
            discarded.append(
                DiscardedSample(
                    sample_date=sample.sample_date,
                    kwh=sample.kwh,
                    reason="future_sample_after_reference_date",
                )
            )
            continue

        if not sample.is_valid:
            discarded.append(
                DiscardedSample(
                    sample_date=sample.sample_date,
                    kwh=sample.kwh,
                    reason=sample.invalid_reason or "marked_invalid",
                )
            )
            continue

        if sample.kwh is None or isinstance(sample.kwh, bool) or not math.isfinite(sample.kwh):
            discarded.append(
                DiscardedSample(
                    sample_date=sample.sample_date,
                    kwh=sample.kwh,
                    reason="non_finite_or_missing_kwh",
                )
            )
            continue

        if sample.kwh < 0:
            discarded.append(
                DiscardedSample(
                    sample_date=sample.sample_date,
                    kwh=sample.kwh,
                    reason="negative_kwh",
                )
            )
            continue

        if sample.sample_date in valid_by_date:
            previous = valid_by_date[sample.sample_date]
            discarded.append(
                DiscardedSample(
                    sample_date=previous.sample_date,
                    kwh=previous.kwh,
                    reason="duplicate_date_superseded",
                )
            )
        valid_by_date[sample.sample_date] = sample

    ordered_valid = sorted(
        valid_by_date.values(),
        key=lambda item: item.sample_date,
        reverse=True,
    )
    selected = tuple(ordered_valid[:lookback_days])

    if len(selected) < min_history_days:
        return LoadEstimationResult(
            is_valid=False,
            status_code=CalculationStatus.INSUFFICIENT_HISTORY,
            reason=(
                f"Insufficient valid daytime load history: found {len(selected)} "
                f"days, require at least {min_history_days}."
            ),
            estimated_kwh=None,
            method=method,
            samples_used=selected,
            samples_discarded=tuple(discarded),
        )

    values = [float(item.kwh) for item in selected if item.kwh is not None]
    if method is EstimationMethod.MEDIAN:
        estimated = float(statistics.median(values))
    elif method is EstimationMethod.MEAN:
        estimated = float(statistics.fmean(values))
    else:
        return LoadEstimationResult(
            is_valid=False,
            status_code=CalculationStatus.INVALID_CONFIG,
            reason=f"Unsupported estimation method: {method!r}.",
            estimated_kwh=None,
            method=method,
            samples_used=selected,
            samples_discarded=tuple(discarded),
        )

    return LoadEstimationResult(
        is_valid=True,
        status_code=CalculationStatus.OK,
        reason=(
            f"Estimated daytime load using {method.value} over {len(selected)} "
            f"valid days (lookback={lookback_days})."
        ),
        estimated_kwh=estimated,
        method=method,
        samples_used=selected,
        samples_discarded=tuple(discarded),
    )
