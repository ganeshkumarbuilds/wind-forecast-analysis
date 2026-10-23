"""Synthetic aligned observations for metric unit tests only."""

import math

import pytest

from app.services.metrics import (
    AlignedObservation,
    MetricsInputError,
    calculate_metrics,
)


def observation(forecast: float, actual: float) -> AlignedObservation:
    """Create one synthetic, explicitly aligned test pair."""
    return AlignedObservation(forecast=forecast, actual=actual)


def test_calculates_correct_mae() -> None:
    result = calculate_metrics(
        [observation(12, 10), observation(8, 10)],
        comparability="verified",
    )

    assert result.mae == 2


def test_calculates_correct_rmse() -> None:
    result = calculate_metrics(
        [observation(12, 10), observation(7, 10)],
        comparability="verified",
    )

    assert result.rmse == pytest.approx(math.sqrt(6.5))


def test_positive_mean_bias_indicates_overforecasting() -> None:
    result = calculate_metrics(
        [observation(12, 10), observation(14, 10)],
        comparability="verified",
    )

    assert result.mean_bias == 3
    assert result.error_sign_convention == "forecast - actual"


def test_negative_mean_bias_indicates_underforecasting() -> None:
    result = calculate_metrics(
        [observation(8, 10), observation(6, 10)],
        comparability="verified",
    )

    assert result.mean_bias == -3


def test_zero_bias_when_over_and_under_forecasts_balance() -> None:
    result = calculate_metrics(
        [observation(12, 10), observation(8, 10)],
        comparability="verified",
    )

    assert result.mean_bias == 0


def test_calculates_mape_as_percentage() -> None:
    result = calculate_metrics(
        [observation(110, 100), observation(180, 200)],
        comparability="verified",
    )

    assert result.mape == pytest.approx(10)
    assert result.mape_status == "available"
    assert result.mape_observation_count == 2
    assert result.zero_actual_excluded_count == 0


def test_zero_actual_is_excluded_from_mape_only() -> None:
    result = calculate_metrics(
        [observation(10, 0), observation(110, 100)],
        comparability="verified",
    )

    assert result.observation_count == 2
    assert result.mae == 10
    assert result.rmse == pytest.approx(math.sqrt(100))
    assert result.mean_bias == 10
    assert result.mape == pytest.approx(10)
    assert result.mape_observation_count == 1
    assert result.zero_actual_excluded_count == 1


def test_all_zero_actuals_make_mape_explicitly_unavailable() -> None:
    result = calculate_metrics(
        [observation(10, 0), observation(20, 0)],
        comparability="verified",
    )

    assert result.mae == 15
    assert result.rmse == pytest.approx(math.sqrt(250))
    assert result.mean_bias == 15
    assert result.mape is None
    assert result.mape_status == "unavailable_zero_actuals"
    assert result.mape_observation_count == 0
    assert result.zero_actual_excluded_count == 2


def test_empty_evaluation_is_rejected() -> None:
    with pytest.raises(MetricsInputError, match="At least one"):
        calculate_metrics([], comparability="verified")


@pytest.mark.parametrize(
    "value",
    [float("nan"), float("inf"), float("-inf")],
)
@pytest.mark.parametrize("field", ["forecast", "actual"])
def test_non_finite_values_are_rejected(value: float, field: str) -> None:
    pair = AlignedObservation(
        forecast=value if field == "forecast" else 1.0,
        actual=value if field == "actual" else 1.0,
    )

    with pytest.raises(MetricsInputError, match="non-finite"):
        calculate_metrics([pair], comparability="verified")


def test_non_numeric_pair_values_are_rejected() -> None:
    pair = AlignedObservation(forecast="100", actual=90)  # type: ignore[arg-type]

    with pytest.raises(MetricsInputError, match="non-numeric"):
        calculate_metrics([pair], comparability="verified")


def test_single_observation_calculates_each_metric() -> None:
    result = calculate_metrics(
        [observation(110, 100)],
        comparability="verified",
        units="caller-verified unit",
    )

    assert result.mae == 10
    assert result.rmse == 10
    assert result.mean_bias == 10
    assert result.mape == pytest.approx(10)
    assert result.observation_count == 1
    assert result.mape_observation_count == 1
    assert result.units == "caller-verified unit"


def test_unverified_comparability_returns_no_metrics() -> None:
    result = calculate_metrics(
        [observation(110, 100)],
        comparability="unverified",
    )

    assert result.status == "comparability_unverified"
    assert result.mae is None
    assert result.rmse is None
    assert result.mean_bias is None
    assert result.mape is None
    assert result.mape_status == "unavailable_comparability_unverified"
    assert result.observation_count == 1
    assert result.mape_observation_count is None
    assert result.zero_actual_excluded_count is None
    assert result.units is None


def test_units_cannot_be_claimed_when_comparability_is_unverified() -> None:
    with pytest.raises(MetricsInputError, match="Units cannot"):
        calculate_metrics(
            [observation(110, 100)],
            comparability="unverified",
            units="MW",
        )


def test_units_are_not_assumed_when_not_supplied() -> None:
    result = calculate_metrics(
        [observation(110, 100)],
        comparability="verified",
    )

    assert result.units is None


def test_rejects_non_aligned_arbitrary_input_objects() -> None:
    with pytest.raises(MetricsInputError, match="AlignedObservation"):
        calculate_metrics(
            [{"forecast": 100, "actual": 90}],  # type: ignore[list-item]
            comparability="verified",
        )


def test_results_are_deterministic_for_same_observations() -> None:
    pairs = [
        observation(110, 100),
        observation(80, 100),
        observation(125, 100),
    ]

    first = calculate_metrics(pairs, comparability="verified")
    second = calculate_metrics(pairs, comparability="verified")

    assert first == second
