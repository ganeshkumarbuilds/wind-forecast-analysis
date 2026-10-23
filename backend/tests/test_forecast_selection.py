"""Synthetic forecast records for forecast-selection unit tests only."""

from datetime import date, datetime, timezone

import pandas as pd
import pytest

from app.services.data_processing import validate_windfor
from app.services.forecast_selection import (
    DecisionContext,
    DecisionDateWindow,
    ForecastSelection,
    ForecastSelectionInputError,
    select_forecasts,
)

DECISION_DATE = date(2026, 1, 15)


def forecast_record(
    start_time: str,
    publish_time: str,
    generation: int,
) -> dict[str, object]:
    """Build a synthetic validated-shape WINDFOR record for tests."""
    return {
        "startTime": start_time,
        "publishTime": publish_time,
        "startTimeUtc": pd.Timestamp(start_time),
        "publishTimeUtc": pd.Timestamp(publish_time),
        "generation": generation,
        "sourceNote": "synthetic test fixture",
    }


def decision_context(
    cutoff: str = "2026-01-15T12:00:00Z",
    decision_date: date = DECISION_DATE,
) -> DecisionContext:
    return DecisionContext(
        decision_date=decision_date,
        cutoff=pd.Timestamp(cutoff),
    )


def select(
    records: list[dict[str, object]],
    *,
    cutoff: str = "2026-01-15T12:00:00Z",
    intervals: list[str] | None = None,
) -> tuple[ForecastSelection, ...]:
    delivery_intervals = (
        ["2026-01-16T00:00:00Z"] if intervals is None else intervals
    )
    return select_forecasts(
        records,
        decision_contexts=[decision_context(cutoff)],
        delivery_intervals=[pd.Timestamp(value) for value in delivery_intervals],
    )


def test_selects_latest_forecast_published_before_cutoff() -> None:
    records = [
        forecast_record(
            "2026-01-16T00:00:00Z",
            "2026-01-15T10:00:00Z",
            100,
        ),
        forecast_record(
            "2026-01-16T00:00:00Z",
            "2026-01-15T11:30:00Z",
            120,
        ),
    ]

    result = select(records)[0]

    assert result.status == "selected"
    assert result.generation == 120
    assert result.publish_time == pd.Timestamp("2026-01-15T11:30:00Z")
    assert result.decision_cutoff == pd.Timestamp("2026-01-15T12:00:00Z")
    assert result.eligible_record_count == 2
    assert "latest publication" in result.rationale


def test_forecasts_published_after_cutoff_are_excluded() -> None:
    records = [
        forecast_record(
            "2026-01-16T00:00:00Z",
            "2026-01-15T11:00:00Z",
            100,
        ),
        forecast_record(
            "2026-01-16T00:00:00Z",
            "2026-01-15T12:00:01Z",
            999,
        ),
    ]

    result = select(records)[0]

    assert result.generation == 100
    assert result.publish_time == pd.Timestamp("2026-01-15T11:00:00Z")
    assert result.eligible_record_count == 1


def test_forecast_published_exactly_at_cutoff_is_not_before_cutoff() -> None:
    result = select(
        [
            forecast_record(
                "2026-01-16T00:00:00Z",
                "2026-01-15T12:00:00Z",
                100,
            )
        ]
    )[0]

    assert result.status == "no_eligible_forecast"
    assert result.generation is None


def test_only_eligible_forecast_is_selected() -> None:
    result = select(
        [
            forecast_record(
                "2026-01-16T00:00:00Z",
                "2026-01-15T11:59:59Z",
                400,
            )
        ]
    )[0]

    assert result.status == "selected"
    assert result.generation == 400
    assert result.eligible_record_count == 1


def test_no_eligible_forecast_is_reported_without_fabricated_value() -> None:
    result = select(
        [
            forecast_record(
                "2026-01-16T00:00:00Z",
                "2026-01-15T12:00:01Z",
                400,
            )
        ]
    )[0]

    assert result.status == "no_eligible_forecast"
    assert result.generation is None
    assert result.publish_time is None
    assert result.eligible_record_count == 0


def test_multiple_delivery_intervals_are_returned_in_sorted_order() -> None:
    records = [
        forecast_record(
            "2026-01-16T01:00:00Z",
            "2026-01-15T10:00:00Z",
            200,
        ),
        forecast_record(
            "2026-01-16T00:00:00Z",
            "2026-01-15T10:00:00Z",
            100,
        ),
    ]

    results = select(
        records,
        intervals=[
            "2026-01-16T01:00:00Z",
            "2026-01-16T00:00:00Z",
        ],
    )

    assert [result.delivery_interval for result in results] == [
        pd.Timestamp("2026-01-16T00:00:00Z"),
        pd.Timestamp("2026-01-16T01:00:00Z"),
    ]
    assert [result.generation for result in results] == [100, 200]


def test_offset_timestamps_are_normalized_before_comparison() -> None:
    records = [
        forecast_record(
            "2026-01-16T02:00:00+02:00",
            "2026-01-15T12:30:00+01:00",
            650,
        )
    ]
    result = select(
        records,
        cutoff="2026-01-15T11:45:00Z",
        intervals=["2026-01-16T00:00:00Z"],
    )[0]

    assert result.status == "selected"
    assert result.delivery_interval == pd.Timestamp("2026-01-16T00:00:00Z")
    assert result.publish_time == pd.Timestamp("2026-01-15T11:30:00Z")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("startTimeUtc", "2026-01-16T00:00:00"),
        ("publishTimeUtc", "2026-01-15T11:00:00"),
    ],
)
def test_naive_forecast_timestamps_are_rejected(
    field: str,
    value: str,
) -> None:
    record = forecast_record(
        "2026-01-16T00:00:00Z",
        "2026-01-15T11:00:00Z",
        100,
    )
    record[field] = value

    with pytest.raises(ForecastSelectionInputError, match="timezone-aware"):
        select([record])


def test_naive_cutoff_is_rejected() -> None:
    with pytest.raises(ForecastSelectionInputError, match="timezone-aware"):
        select_forecasts(
            [],
            decision_contexts=[
                DecisionContext(
                    decision_date=DECISION_DATE,
                    cutoff=datetime(2026, 1, 15, 12, 0),
                )
            ],
            delivery_intervals=[pd.Timestamp("2026-01-16T00:00:00Z")],
        )


def test_exact_duplicates_do_not_increase_eligible_count() -> None:
    row = forecast_record(
        "2026-01-16T00:00:00Z",
        "2026-01-15T11:00:00Z",
        150,
    )

    result = select([row, dict(row)])[0]

    assert result.status == "selected"
    assert result.generation == 150
    assert result.eligible_record_count == 1
    assert result.duplicate_information[0].kind == "exact"
    assert result.duplicate_information[0].record_count == 2


def test_conflicting_duplicate_latest_publications_are_ambiguous() -> None:
    report = validate_windfor(
        [
            {
                "startTime": "2026-01-16T00:00:00Z",
                "publishTime": "2026-01-15T11:00:00Z",
                "generation": 150,
            },
            {
                "startTime": "2026-01-16T00:00:00Z",
                "publishTime": "2026-01-15T11:00:00Z",
                "generation": 175,
            },
        ]
    )

    result = select_forecasts(
        report,
        decision_contexts=[decision_context()],
        delivery_intervals=[pd.Timestamp("2026-01-16T00:00:00Z")],
    )[0]

    assert report.duplicates[0].kind == "conflicting"
    assert result.status == "ambiguous"
    assert result.generation is None
    assert result.publish_time == pd.Timestamp("2026-01-15T11:00:00Z")
    assert result.duplicate_information[0].kind == "conflicting"


def test_reordered_input_produces_deterministic_selections() -> None:
    records = [
        forecast_record(
            "2026-01-16T00:00:00Z",
            "2026-01-15T10:00:00Z",
            100,
        ),
        forecast_record(
            "2026-01-16T00:00:00Z",
            "2026-01-15T11:00:00Z",
            200,
        ),
    ]

    first = select(records)
    second = select(list(reversed(records)))

    assert first == second


def test_selected_generation_and_original_timestamps_are_preserved() -> None:
    record = forecast_record(
        "2026-01-16T02:00:00+02:00",
        "2026-01-15T12:30:00+01:00",
        12345,
    )

    result = select(
        [record],
        cutoff="2026-01-15T11:45:00Z",
        intervals=["2026-01-16T00:00:00Z"],
    )[0]

    assert result.generation == record["generation"]
    assert result.original_start_time == record["startTime"]
    assert result.original_publish_time == record["publishTime"]


def test_january_decision_window_keeps_february_delivery_interval() -> None:
    february_start = pd.Timestamp("2026-02-01T00:00:00Z")
    context = decision_context(
        cutoff="2026-01-31T22:00:00Z",
        decision_date=date(2026, 1, 31),
    )
    records = [
        forecast_record(
            "2026-02-01T00:00:00Z",
            "2026-01-31T21:30:00Z",
            720,
        )
    ]

    results = select_forecasts(
        records,
        decision_contexts=[context],
        decision_date_window=DecisionDateWindow(
            date(2026, 1, 1),
            date(2026, 1, 31),
        ),
        delivery_intervals=[february_start],
    )

    assert len(results) == 1
    assert results[0].decision_date == date(2026, 1, 31)
    assert results[0].delivery_interval == february_start
    assert results[0].status == "selected"
    assert results[0].generation == 720


def test_decision_date_window_filters_contexts_not_delivery_dates() -> None:
    contexts = [
        decision_context(
            "2026-01-15T12:00:00Z",
            date(2026, 1, 15),
        ),
        decision_context(
            "2026-02-01T12:00:00Z",
            date(2026, 2, 1),
        ),
    ]

    results = select_forecasts(
        [],
        decision_contexts=contexts,
        decision_date_window=DecisionDateWindow(
            date(2026, 1, 1),
            date(2026, 1, 31),
        ),
        delivery_intervals=[pd.Timestamp("2026-02-01T00:00:00Z")],
    )

    assert len(results) == 1
    assert results[0].decision_date == date(2026, 1, 15)
    assert results[0].status == "no_eligible_forecast"


def test_naive_delivery_interval_is_rejected() -> None:
    with pytest.raises(ForecastSelectionInputError, match="timezone-aware"):
        select_forecasts(
            [],
            decision_contexts=[decision_context()],
            delivery_intervals=[datetime(2026, 1, 16)],
        )


def test_ambiguous_negative_zero_offset_is_rejected() -> None:
    record = forecast_record(
        "2026-01-16T00:00:00Z",
        "2026-01-15T11:00:00Z",
        100,
    )
    record["publishTimeUtc"] = "2026-01-15T11:00:00-00:00"

    with pytest.raises(ForecastSelectionInputError, match="ambiguous"):
        select([record])
