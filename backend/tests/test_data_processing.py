"""Synthetic unit-test records; no live Elexon data is used."""

from collections.abc import Callable
from datetime import timezone

import pandas as pd
import pytest

from app.services.data_processing import (
    ValidationReport,
    validate_fuelhh,
    validate_windfor,
)


def fuelhh_record(**overrides: object) -> dict[str, object]:
    """Build synthetic FUELHH input for unit tests."""
    record: dict[str, object] = {
        "fuelType": "WIND",
        "startTime": "2026-01-01T00:00:00Z",
        "generation": 1250,
        "sourceNote": "synthetic test fixture",
    }
    record.update(overrides)
    return record


def windfor_record(**overrides: object) -> dict[str, object]:
    """Build synthetic WINDFOR input for unit tests."""
    record: dict[str, object] = {
        "startTime": "2026-01-01T01:00:00Z",
        "publishTime": "2026-01-01T00:30:00Z",
        "generation": 1300,
        "sourceNote": "synthetic test fixture",
    }
    record.update(overrides)
    return record


def test_valid_fuelhh_record_preserves_source_and_normalizes_start_time() -> None:
    source = fuelhh_record()

    report = validate_fuelhh([source])

    assert report.dataset == "FUELHH"
    assert len(report.records) == 1
    assert report.records[0]["startTime"] == source["startTime"]
    assert report.records[0]["sourceNote"] == source["sourceNote"]
    assert report.records[0]["startTimeUtc"] == pd.Timestamp(
        "2026-01-01T00:00:00Z"
    )
    assert report.records[0]["startTimeUtc"].tz == timezone.utc
    assert report.rejected == ()


def test_non_wind_fuelhh_record_is_reported_as_excluded() -> None:
    report = validate_fuelhh([fuelhh_record(fuelType="GAS")])

    assert report.records == ()
    assert report.rejected == ()
    assert len(report.excluded) == 1
    assert report.excluded[0].reason == "non_wind_fuel_type"


def test_valid_windfor_preserves_original_timestamps_and_adds_utc_values() -> None:
    source = windfor_record()

    report = validate_windfor([source])

    normalized = report.records[0]
    assert normalized["startTime"] == source["startTime"]
    assert normalized["publishTime"] == source["publishTime"]
    assert normalized["startTimeUtc"] == pd.Timestamp(source["startTime"])
    assert normalized["publishTimeUtc"] == pd.Timestamp(source["publishTime"])
    assert normalized["startTimeUtc"].tz == timezone.utc


def test_explicit_non_utc_offsets_are_converted_to_utc() -> None:
    report = validate_windfor(
        [
            windfor_record(
                startTime="2026-01-01T03:00:00+02:00",
                publishTime="2025-12-31T19:30:00-05:00",
            )
        ]
    )

    normalized = report.records[0]
    assert normalized["startTimeUtc"] == pd.Timestamp(
        "2026-01-01T01:00:00Z"
    )
    assert normalized["publishTimeUtc"] == pd.Timestamp(
        "2026-01-01T00:30:00Z"
    )


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("startTime", "not-a-timestamp", "startTime_invalid"),
        ("publishTime", "not-a-timestamp", "publishTime_invalid"),
        ("startTime", "2026-01-01T00:00:00", "startTime_timezone_naive"),
        ("publishTime", "2026-01-01T00:00:00", "publishTime_timezone_naive"),
        (
            "startTime",
            "2026-01-01T00:00:00-00:00",
            "startTime_timezone_ambiguous",
        ),
    ],
)
def test_invalid_or_ambiguous_windfor_timestamps_are_rejected(
    field: str,
    value: str,
    reason: str,
) -> None:
    report = validate_windfor([windfor_record(**{field: value})])

    assert report.records == ()
    assert report.rejected[0].reasons == (reason,)


@pytest.mark.parametrize(
    ("record", "reason"),
    [
        (
            {"fuelType": "WIND", "generation": 1},
            "missing_startTime",
        ),
        (
            {"fuelType": "WIND", "startTime": "2026-01-01T00:00:00Z"},
            "missing_generation",
        ),
    ],
)
def test_fuelhh_missing_required_fields_are_reported(
    record: dict[str, object],
    reason: str,
) -> None:
    report = validate_fuelhh([record])

    assert report.records == ()
    assert reason in report.rejected[0].reasons


@pytest.mark.parametrize(
    ("record", "reasons"),
    [
        (
            {
                "publishTime": "2026-01-01T00:30:00Z",
                "generation": 1,
            },
            ("missing_startTime",),
        ),
        (
            {
                "startTime": "2026-01-01T01:00:00Z",
                "publishTime": "2026-01-01T00:30:00Z",
            },
            ("missing_generation",),
        ),
    ],
)
def test_windfor_missing_required_fields_are_reported(
    record: dict[str, object],
    reasons: tuple[str, ...],
) -> None:
    report = validate_windfor([record])

    assert report.records == ()
    assert report.rejected[0].reasons == reasons


@pytest.mark.parametrize(
    ("generation", "reason"),
    [
        ("123", "generation_not_numeric"),
        (None, "generation_not_numeric"),
        (True, "generation_not_numeric"),
        (float("nan"), "generation_not_finite"),
        (float("inf"), "generation_not_finite"),
        (float("-inf"), "generation_not_finite"),
    ],
)
@pytest.mark.parametrize(
    ("validator", "record_factory"),
    [
        (validate_fuelhh, fuelhh_record),
        (validate_windfor, windfor_record),
    ],
)
def test_invalid_generation_values_are_reported(
    validator: Callable[
        [list[dict[str, object]]],
        ValidationReport,
    ],
    record_factory: Callable[..., dict[str, object]],
    generation: object,
    reason: str,
) -> None:
    report = validator([record_factory(generation=generation)])

    assert report.records == ()
    assert report.rejected[0].reasons == (reason,)
    assert report.rejected[0].record["generation"] is generation


def test_identical_duplicate_windfor_records_are_classified_exact() -> None:
    record = windfor_record()

    report = validate_windfor([record, dict(record)])

    assert len(report.records) == 2
    assert len(report.duplicates) == 1
    assert report.duplicates[0].kind == "exact"
    assert report.duplicates[0].indices == (0, 1)


def test_same_key_windfor_records_with_different_values_are_conflicting() -> None:
    first = windfor_record()
    second = windfor_record(generation=1400)

    report = validate_windfor([first, second])

    assert len(report.records) == 2
    assert len(report.duplicates) == 1
    assert report.duplicates[0].kind == "conflicting"
    assert report.duplicates[0].indices == (0, 1)


def test_identical_duplicate_fuelhh_records_are_classified_exact() -> None:
    record = fuelhh_record()

    report = validate_fuelhh([record, dict(record)])

    assert len(report.records) == 2
    assert report.duplicates[0].kind == "exact"
    assert report.duplicates[0].indices == (0, 1)


def test_same_key_fuelhh_records_with_different_values_are_conflicting() -> None:
    report = validate_fuelhh(
        [fuelhh_record(), fuelhh_record(generation=1400)]
    )

    assert len(report.records) == 2
    assert report.duplicates[0].kind == "conflicting"
    assert report.duplicates[0].indices == (0, 1)


def test_empty_inputs_return_empty_quality_reports() -> None:
    fuelhh_report = validate_fuelhh([])
    windfor_report = validate_windfor([])

    assert fuelhh_report.records == ()
    assert fuelhh_report.rejected == ()
    assert fuelhh_report.excluded == ()
    assert fuelhh_report.duplicates == ()
    assert windfor_report.records == ()
    assert windfor_report.rejected == ()
    assert windfor_report.duplicates == ()


def test_timezone_naive_fuelhh_timestamp_is_not_assumed_utc() -> None:
    report = validate_fuelhh(
        [fuelhh_record(startTime="2026-01-01T00:00:00")]
    )

    assert report.records == ()
    assert report.rejected[0].reasons == ("startTime_timezone_naive",)


def test_timezone_naive_windfor_publish_time_is_not_assumed_utc() -> None:
    report = validate_windfor(
        [windfor_record(publishTime="2026-01-01T00:30:00")]
    )

    assert report.records == ()
    assert report.rejected[0].reasons == ("publishTime_timezone_naive",)
