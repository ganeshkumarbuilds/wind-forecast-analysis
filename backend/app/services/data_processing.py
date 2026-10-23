"""Validation and UTC normalization for Elexon generation records.

Normalized records retain their source fields and add UTC pandas timestamps.
This module does not infer generation units or transform interval resolution.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from numbers import Real
from typing import Any, Literal

import pandas as pd

RawRecord = Mapping[str, Any]
NormalizedRecord = dict[str, Any]


@dataclass(frozen=True)
class RejectedRecord:
    """A source row rejected during validation, with stable reason codes."""

    index: int
    record: object
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class ExcludedRecord:
    """A validly identified non-WIND FUELHH row excluded by dataset scope."""

    index: int
    record: RawRecord
    reason: str


@dataclass(frozen=True)
class DuplicateGroup:
    """Records sharing a dataset key, classified without choosing a winner."""

    key: tuple[object, ...]
    indices: tuple[int, ...]
    kind: Literal["exact", "conflicting"]


@dataclass(frozen=True)
class ValidationReport:
    """Accepted normalized rows and explicit data-quality findings."""

    dataset: Literal["FUELHH", "WINDFOR"]
    records: tuple[NormalizedRecord, ...]
    rejected: tuple[RejectedRecord, ...]
    duplicates: tuple[DuplicateGroup, ...]
    excluded: tuple[ExcludedRecord, ...] = ()


def validate_fuelhh(
    records: Iterable[RawRecord],
) -> ValidationReport:
    """Validate FUELHH rows, retaining and normalizing WIND rows only.

    Non-WIND rows are listed as excluded rather than rejected. The duplicate
    key uses the normalized delivery start and, when present, the source
    publication time so distinct published outturn versions are not collapsed.
    """
    accepted: list[tuple[int, NormalizedRecord, RawRecord]] = []
    rejected: list[RejectedRecord] = []
    excluded: list[ExcludedRecord] = []

    for index, record in enumerate(records):
        if not isinstance(record, Mapping):
            rejected.append(
                RejectedRecord(index, record, ("record_not_object",))
            )
            continue

        source = dict(record)
        fuel_type = source.get("fuelType")
        if "fuelType" not in source:
            rejected.append(
                RejectedRecord(index, source, ("missing_fuelType",))
            )
            continue
        if not isinstance(fuel_type, str):
            rejected.append(
                RejectedRecord(index, source, ("invalid_fuelType",))
            )
            continue
        if fuel_type != "WIND":
            excluded.append(
                ExcludedRecord(index, source, "non_wind_fuel_type")
            )
            continue

        reasons: list[str] = []
        normalized = dict(source)
        _validate_generation(source, reasons)
        if "startTime" not in source:
            reasons.append("missing_startTime")
        else:
            timestamp, reason = _parse_utc_timestamp(source["startTime"])
            if reason is not None:
                reasons.append(f"startTime_{reason}")
            else:
                normalized["startTimeUtc"] = timestamp

        if reasons:
            rejected.append(RejectedRecord(index, source, tuple(reasons)))
            continue

        accepted.append((index, normalized, source))

    duplicates = _find_duplicates(
        accepted,
        key_for=_fuelhh_duplicate_key,
    )
    return ValidationReport(
        dataset="FUELHH",
        records=tuple(row for _, row, _ in accepted),
        rejected=tuple(rejected),
        duplicates=duplicates,
        excluded=tuple(excluded),
    )


def validate_windfor(
    records: Iterable[RawRecord],
) -> ValidationReport:
    """Validate WINDFOR rows and add normalized UTC timestamps.

    Source timestamp strings remain unchanged in ``startTime`` and
    ``publishTime``. Normalized values are exposed as ``startTimeUtc`` and
    ``publishTimeUtc``. Duplicate identity is the delivery/publication pair.
    """
    accepted: list[tuple[int, NormalizedRecord, RawRecord]] = []
    rejected: list[RejectedRecord] = []

    for index, record in enumerate(records):
        if not isinstance(record, Mapping):
            rejected.append(
                RejectedRecord(index, record, ("record_not_object",))
            )
            continue

        source = dict(record)
        normalized = dict(source)
        reasons: list[str] = []
        _validate_generation(source, reasons)
        for field in ("startTime", "publishTime"):
            if field not in source:
                reasons.append(f"missing_{field}")
                continue
            timestamp, reason = _parse_utc_timestamp(source[field])
            if reason is not None:
                reasons.append(f"{field}_{reason}")
            else:
                normalized[f"{field}Utc"] = timestamp

        if reasons:
            rejected.append(RejectedRecord(index, source, tuple(reasons)))
            continue

        accepted.append((index, normalized, source))

    duplicates = _find_duplicates(
        accepted,
        key_for=lambda row: (
            row["startTimeUtc"],
            row["publishTimeUtc"],
        ),
    )
    return ValidationReport(
        dataset="WINDFOR",
        records=tuple(row for _, row, _ in accepted),
        rejected=tuple(rejected),
        duplicates=duplicates,
    )


def _validate_generation(
    source: RawRecord,
    reasons: list[str],
) -> None:
    if "generation" not in source:
        reasons.append("missing_generation")
        return

    generation = source["generation"]
    if isinstance(generation, bool) or not isinstance(generation, Real):
        reasons.append("generation_not_numeric")
        return
    if not math.isfinite(generation):
        reasons.append("generation_not_finite")


def _parse_utc_timestamp(
    value: object,
) -> tuple[pd.Timestamp | None, str | None]:
    if not isinstance(value, str):
        return None, "invalid"

    timestamp_text = value.strip()
    if timestamp_text.endswith("-00:00"):
        return None, "timezone_ambiguous"

    if timestamp_text.endswith("Z"):
        timestamp_text = f"{timestamp_text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(timestamp_text)
    except ValueError:
        return None, "invalid"

    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None, "timezone_naive"

    try:
        return pd.Timestamp(parsed).tz_convert("UTC"), None
    except (OverflowError, ValueError, pd.errors.OutOfBoundsDatetime):
        return None, "invalid"


def _find_duplicates(
    accepted: list[tuple[int, NormalizedRecord, RawRecord]],
    *,
    key_for: Callable[[NormalizedRecord], tuple[object, ...]],
) -> tuple[DuplicateGroup, ...]:
    grouped: dict[
        tuple[object, ...],
        list[tuple[int, NormalizedRecord, RawRecord]],
    ] = defaultdict(list)
    for item in accepted:
        grouped[key_for(item[1])].append(item)

    duplicates: list[DuplicateGroup] = []
    for key, group in grouped.items():
        if len(group) < 2:
            continue
        first_source = group[0][2]
        kind: Literal["exact", "conflicting"] = (
            "exact"
            if all(source == first_source for _, _, source in group[1:])
            else "conflicting"
        )
        duplicates.append(
            DuplicateGroup(
                key=key,
                indices=tuple(index for index, _, _ in group),
                kind=kind,
            )
        )
    return tuple(duplicates)


def _fuelhh_duplicate_key(
    record: NormalizedRecord,
) -> tuple[object, ...]:
    publish_time = record.get("publishTime")
    return (
        record["startTimeUtc"],
        publish_time if isinstance(publish_time, str) else None,
    )
