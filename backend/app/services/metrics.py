"""Forecast accuracy metrics for explicitly aligned numeric observations.

This module does not align Elexon intervals or establish that FUELHH and
WINDFOR values are comparable. Callers must supply already-aligned pairs and
explicitly state whether comparability has been verified.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from numbers import Real
from typing import Literal

Comparability = Literal["verified", "unverified"]
MetricsStatus = Literal["calculated", "comparability_unverified"]
MapeStatus = Literal[
    "available",
    "unavailable_zero_actuals",
    "unavailable_comparability_unverified",
]


class MetricsInputError(ValueError):
    """Raised when metric observations or comparability metadata are invalid."""


class MetricsCalculationError(ArithmeticError):
    """Raised if valid finite inputs produce unrepresentable metrics."""


@dataclass(frozen=True)
class AlignedObservation:
    """One forecast and actual pair already aligned to an approved interval.

    Constructing this value does not itself verify that units or interval
    semantics are comparable; the metric caller must provide that status.
    """

    forecast: Real
    actual: Real


@dataclass(frozen=True)
class AccuracyMetrics:
    """Accuracy statistics and the sample/comparability state they describe."""

    status: MetricsStatus
    mae: float | None
    rmse: float | None
    mean_bias: float | None
    mape: float | None
    mape_status: MapeStatus
    observation_count: int
    mape_observation_count: int | None
    zero_actual_excluded_count: int | None
    error_sign_convention: str
    units: str | None


def calculate_metrics(
    observations: Iterable[AlignedObservation],
    *,
    comparability: Comparability,
    units: str | None = None,
) -> AccuracyMetrics:
    """Calculate MAE, RMSE, mean bias, and MAPE for aligned pairs.

    Errors use ``forecast - actual``. MAPE excludes zero-actual observations
    from its denominator only. If comparability is unverified, this function
    validates the supplied pairs but returns no metric values; it never
    implies that real Elexon forecast and actual records are comparable.

    The caller may provide ``units`` only when those units are verified for
    the supplied comparison. Units are not inferred or defaulted.
    """
    if comparability not in ("verified", "unverified"):
        raise MetricsInputError(
            "comparability must be 'verified' or 'unverified'."
        )
    if units is not None:
        if not units.strip():
            raise MetricsInputError("units must be non-empty when supplied.")
        if comparability != "verified":
            raise MetricsInputError(
                "Units cannot be reported when comparability is unverified."
            )

    pairs = tuple(observations)
    if not pairs:
        raise MetricsInputError("At least one aligned observation is required.")

    validated: list[tuple[float, float]] = []
    for index, pair in enumerate(pairs):
        if not isinstance(pair, AlignedObservation):
            raise MetricsInputError(
                f"Observation at index {index} must be an AlignedObservation."
            )
        validated.append(
            (
                _finite_float(pair.forecast, index, "forecast"),
                _finite_float(pair.actual, index, "actual"),
            )
        )

    if comparability == "unverified":
        return AccuracyMetrics(
            status="comparability_unverified",
            mae=None,
            rmse=None,
            mean_bias=None,
            mape=None,
            mape_status="unavailable_comparability_unverified",
            observation_count=len(validated),
            mape_observation_count=None,
            zero_actual_excluded_count=None,
            error_sign_convention="forecast - actual",
            units=None,
        )

    errors = [
        forecast - actual
        for forecast, actual in validated
    ]
    try:
        mae = math.fsum(abs(error) for error in errors) / len(errors)
        mean_bias = math.fsum(errors) / len(errors)
        rmse = math.sqrt(math.fsum(error * error for error in errors) / len(errors))
    except (OverflowError, ValueError) as exc:
        raise MetricsCalculationError(
            "Metric calculation overflowed for the supplied finite values."
        ) from exc

    mape_terms: list[float] = []
    zero_actual_count = 0
    for (forecast, actual), error in zip(validated, errors, strict=True):
        if actual == 0:
            zero_actual_count += 1
            continue
        try:
            mape_terms.append(abs(error / actual))
        except (OverflowError, ZeroDivisionError) as exc:
            raise MetricsCalculationError(
                "MAPE calculation overflowed for the supplied values."
            ) from exc

    mape_status: MapeStatus
    mape: float | None
    if mape_terms:
        try:
            mape = math.fsum(mape_terms) / len(mape_terms) * 100
        except (OverflowError, ValueError) as exc:
            raise MetricsCalculationError(
                "MAPE calculation overflowed for the supplied values."
            ) from exc
        mape_status = "available"
    else:
        mape = None
        mape_status = "unavailable_zero_actuals"

    metric_values = (mae, rmse, mean_bias)
    if not all(math.isfinite(value) for value in metric_values) or (
        mape is not None and not math.isfinite(mape)
    ):
        raise MetricsCalculationError(
            "Metric calculation produced a non-finite result."
        )

    return AccuracyMetrics(
        status="calculated",
        mae=mae,
        rmse=rmse,
        mean_bias=mean_bias,
        mape=mape,
        mape_status=mape_status,
        observation_count=len(validated),
        mape_observation_count=len(mape_terms),
        zero_actual_excluded_count=zero_actual_count,
        error_sign_convention="forecast - actual",
        units=units,
    )


def _finite_float(value: object, index: int, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise MetricsInputError(
            f"Observation at index {index} has a non-numeric {field}."
        )
    try:
        converted = float(value)
    except (OverflowError, ValueError) as exc:
        raise MetricsInputError(
            f"Observation at index {index} has an invalid {field}."
        ) from exc
    if not math.isfinite(converted):
        raise MetricsInputError(
            f"Observation at index {index} has a non-finite {field}."
        )
    return converted
