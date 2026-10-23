"""Select historical WINDFOR records using explicit decision cutoffs."""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from numbers import Real
from typing import Any, Literal

import pandas as pd

from app.services.data_processing import DuplicateGroup, ValidationReport

ForecastRecord = Mapping[str, Any]


class ForecastSelectionInputError(ValueError):
    """Raised when records or decision inputs are invalid or timezone-ambiguous."""


@dataclass(frozen=True)
class DecisionContext:
    """One business decision and its explicitly supplied cutoff instant.

    ``decision_date`` is the already-classified business date. This service
    does not infer a local timezone or cutoff rule from that date.
    """

    decision_date: date
    cutoff: datetime | pd.Timestamp


@dataclass(frozen=True)
class DecisionDateWindow:
    """Inclusive decision-date window, independent of delivery dates."""

    start_date: date
    end_date: date

    def __post_init__(self) -> None:
        if any(
            not isinstance(value, date) or isinstance(value, datetime)
            for value in (self.start_date, self.end_date)
        ):
            raise ForecastSelectionInputError(
                "Decision-date window bounds must be dates, not datetimes."
            )
        if self.start_date > self.end_date:
            raise ForecastSelectionInputError(
                "Decision-date window start_date must not be after end_date."
            )


@dataclass(frozen=True)
class DuplicateInformation:
    """Duplicate publication detail relevant to a selection."""

    publish_time: pd.Timestamp
    kind: Literal["exact", "conflicting"]
    record_count: int


@dataclass(frozen=True)
class ForecastSelection:
    """Selection result for a decision context and delivery interval."""

    decision_date: date
    delivery_interval: pd.Timestamp
    original_start_time: Any | None
    generation: Real | None
    publish_time: pd.Timestamp | None
    original_publish_time: Any | None
    decision_cutoff: pd.Timestamp
    status: Literal["selected", "no_eligible_forecast", "ambiguous"]
    rationale: str
    eligible_record_count: int
    duplicate_information: tuple[DuplicateInformation, ...]


@dataclass(frozen=True)
class _Candidate:
    record: ForecastRecord
    start_time: pd.Timestamp
    publish_time: pd.Timestamp


def select_forecasts(
    records: ValidationReport | Iterable[ForecastRecord],
    *,
    decision_contexts: Sequence[DecisionContext],
    delivery_intervals: Iterable[datetime | pd.Timestamp],
    decision_date_window: DecisionDateWindow | None = None,
) -> tuple[ForecastSelection, ...]:
    """Select the latest eligible forecast per decision and delivery interval.

    The cutoff is exclusive: only records with ``publishTimeUtc`` strictly
    earlier than the cutoff are eligible. Every context's cutoff must be
    supplied as a timezone-aware instant. A supplied
    decision-date window filters decision contexts only; it never filters
    delivery intervals, so February delivery can remain in a January cohort.

    If ``records`` is a WINDFOR ``ValidationReport``, its duplicate
    classifications are used. Iterable input is independently checked and
    grouped by the normalized delivery/publication timestamps. Exact duplicate
    rows count as one eligible forecast. Conflicting rows at the latest
    eligible publication make that selection ambiguous rather than choosing
    one.
    """
    forecast_rows, supplied_duplicates = _unpack_records(records)
    candidates = tuple(_validate_candidate(record) for record in forecast_rows)
    contexts = _filter_contexts(decision_contexts, decision_date_window)
    intervals = _normalize_intervals(delivery_intervals)

    groups: dict[
        tuple[pd.Timestamp, pd.Timestamp],
        list[_Candidate],
    ] = defaultdict(list)
    for candidate in candidates:
        groups[(candidate.start_time, candidate.publish_time)].append(candidate)

    classified = _classify_duplicate_groups(groups, supplied_duplicates)
    results: list[ForecastSelection] = []
    for context, cutoff in contexts:
        for interval in intervals:
            eligible_keys = sorted(
                (
                    key
                    for key in groups
                    if key[0] == interval and key[1] < cutoff
                ),
                key=lambda key: key[1],
            )
            duplicate_details = tuple(
                DuplicateInformation(
                    publish_time=key[1],
                    kind=classified[key],
                    record_count=len(groups[key]),
                )
                for key in eligible_keys
                if key in classified
            )
            eligible_count = sum(
                1 if classified.get(key) == "exact" else len(groups[key])
                for key in eligible_keys
            )

            if not eligible_keys:
                results.append(
                    ForecastSelection(
                        decision_date=context.decision_date,
                        delivery_interval=interval,
                        original_start_time=None,
                        generation=None,
                        publish_time=None,
                        original_publish_time=None,
                        decision_cutoff=cutoff,
                        status="no_eligible_forecast",
                        rationale=(
                            "No forecast for this delivery interval was "
                            "published strictly before the decision cutoff."
                        ),
                        eligible_record_count=0,
                        duplicate_information=(),
                    )
                )
                continue

            latest_key = eligible_keys[-1]
            duplicate_kind = classified.get(latest_key)
            if duplicate_kind == "conflicting":
                results.append(
                    ForecastSelection(
                        decision_date=context.decision_date,
                        delivery_interval=interval,
                        original_start_time=groups[latest_key][0].record.get(
                            "startTime"
                        ),
                        generation=None,
                        publish_time=latest_key[1],
                        original_publish_time=groups[latest_key][0].record.get(
                            "publishTime"
                        ),
                        decision_cutoff=cutoff,
                        status="ambiguous",
                        rationale=(
                            "Conflicting records share the latest eligible "
                            "delivery interval and publication timestamp."
                        ),
                        eligible_record_count=eligible_count,
                        duplicate_information=duplicate_details,
                    )
                )
                continue

            selected = groups[latest_key][0].record
            generation = selected["generation"]
            results.append(
                ForecastSelection(
                    decision_date=context.decision_date,
                    delivery_interval=interval,
                    original_start_time=selected.get("startTime"),
                    generation=generation,
                    publish_time=latest_key[1],
                    original_publish_time=selected.get("publishTime"),
                    decision_cutoff=cutoff,
                    status="selected",
                    rationale=(
                        "Selected the latest publication strictly before the "
                        "explicit decision cutoff."
                    ),
                    eligible_record_count=eligible_count,
                    duplicate_information=duplicate_details,
                )
            )

    return tuple(results)


def _unpack_records(
    records: ValidationReport | Iterable[ForecastRecord],
) -> tuple[tuple[ForecastRecord, ...], tuple[DuplicateGroup, ...]]:
    if isinstance(records, ValidationReport):
        if records.dataset != "WINDFOR":
            raise ForecastSelectionInputError(
                "Forecast selection requires a WINDFOR validation report."
            )
        return records.records, records.duplicates
    return tuple(records), ()


def _validate_candidate(record: ForecastRecord) -> _Candidate:
    if not isinstance(record, Mapping):
        raise ForecastSelectionInputError(
            "Each forecast record must be a mapping."
        )
    required = ("startTimeUtc", "publishTimeUtc", "generation")
    missing = [field for field in required if field not in record]
    if missing:
        raise ForecastSelectionInputError(
            "Forecast record is missing required fields: "
            + ", ".join(missing)
            + "."
        )

    start_time = _normalize_aware_timestamp(
        record["startTimeUtc"],
        field="startTimeUtc",
    )
    publish_time = _normalize_aware_timestamp(
        record["publishTimeUtc"],
        field="publishTimeUtc",
    )
    generation = record["generation"]
    if (
        isinstance(generation, bool)
        or not isinstance(generation, Real)
        or not math.isfinite(generation)
    ):
        raise ForecastSelectionInputError(
            "Forecast generation must be a finite numeric value."
        )

    return _Candidate(record, start_time, publish_time)


def _filter_contexts(
    contexts: Sequence[DecisionContext],
    window: DecisionDateWindow | None,
) -> tuple[tuple[DecisionContext, pd.Timestamp], ...]:
    if not contexts:
        raise ForecastSelectionInputError(
            "At least one decision context with an explicit cutoff is required."
        )

    filtered: list[tuple[DecisionContext, pd.Timestamp]] = []
    for context in contexts:
        if not isinstance(context, DecisionContext):
            raise ForecastSelectionInputError(
                "Decision contexts must be DecisionContext values."
            )
        if not isinstance(context.decision_date, date) or isinstance(
            context.decision_date, datetime
        ):
            raise ForecastSelectionInputError(
                "decision_date must be a date, not a datetime."
            )
        cutoff = _normalize_aware_timestamp(
            context.cutoff,
            field="decision cutoff",
        )
        if window is None or (
            window.start_date <= context.decision_date <= window.end_date
        ):
            filtered.append((context, cutoff))

    if window is not None and not filtered:
        raise ForecastSelectionInputError(
            "No decision contexts fall within the requested date window."
        )
    return tuple(
        sorted(filtered, key=lambda item: (item[0].decision_date, item[1]))
    )


def _normalize_intervals(
    intervals: Iterable[datetime | pd.Timestamp],
) -> tuple[pd.Timestamp, ...]:
    normalized = {
        _normalize_aware_timestamp(value, field="delivery interval")
        for value in intervals
    }
    return tuple(sorted(normalized))


def _normalize_aware_timestamp(
    value: object,
    *,
    field: str,
) -> pd.Timestamp:
    if isinstance(value, str) and value.strip().endswith("-00:00"):
        raise ForecastSelectionInputError(
            f"{field} has an ambiguous -00:00 timezone offset."
        )
    try:
        timestamp = pd.Timestamp(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ForecastSelectionInputError(
            f"{field} is not a valid timestamp."
        ) from exc
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ForecastSelectionInputError(
            f"{field} must be timezone-aware; naive timestamps are ambiguous."
        )
    try:
        return timestamp.tz_convert("UTC")
    except (TypeError, ValueError, OverflowError, pd.errors.OutOfBoundsDatetime) as exc:
        raise ForecastSelectionInputError(
            f"{field} cannot be safely normalized to UTC."
        ) from exc


def _classify_duplicate_groups(
    groups: Mapping[tuple[pd.Timestamp, pd.Timestamp], list[_Candidate]],
    supplied: tuple[DuplicateGroup, ...],
) -> dict[
    tuple[pd.Timestamp, pd.Timestamp],
    Literal["exact", "conflicting"],
]:
    supplied_by_key: dict[
        tuple[pd.Timestamp, pd.Timestamp],
        Literal["exact", "conflicting"],
    ] = {}
    for duplicate in supplied:
        if len(duplicate.key) != 2:
            continue
        try:
            key = (
                _normalize_aware_timestamp(
                    duplicate.key[0],
                    field="duplicate delivery interval",
                ),
                _normalize_aware_timestamp(
                    duplicate.key[1],
                    field="duplicate publication timestamp",
                ),
            )
        except ForecastSelectionInputError as exc:
            raise ForecastSelectionInputError(
                "Duplicate classifications contain an invalid timestamp."
            ) from exc
        supplied_by_key[key] = duplicate.kind

    classified: dict[
        tuple[pd.Timestamp, pd.Timestamp],
        Literal["exact", "conflicting"],
    ] = {}
    for key, group in groups.items():
        if len(group) < 2:
            continue
        if key in supplied_by_key:
            classified[key] = supplied_by_key[key]
            continue
        first_record = dict(group[0].record)
        exact = all(dict(item.record) == first_record for item in group[1:])
        classified[key] = "exact" if exact else "conflicting"
    return classified
