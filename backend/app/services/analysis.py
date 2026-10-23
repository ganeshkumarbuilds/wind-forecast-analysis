"""Orchestrate Elexon retrieval and safe, metrics-blocked analysis output."""

from __future__ import annotations

import pandas as pd

from app.schemas.analysis import (
    AnalysisRequest,
    AnalysisResponse,
    DataQualityResponse,
    DuplicateInfoResponse,
    SelectedForecastResponse,
)
from app.services.data_processing import validate_fuelhh, validate_windfor
from app.services.elexon_client import ElexonClient
from app.services.forecast_selection import (
    DecisionContext,
    DecisionDateWindow,
    ForecastSelectionInputError,
    select_forecasts,
)

METRICS_BLOCK_REASON = (
    "Metrics are blocked because WINDFOR generation units and interval "
    "semantics have not been verified, and sampled forecasts are hourly "
    "while FUELHH actuals are half-hourly. No forecast/actual alignment or "
    "accuracy calculation was performed."
)
MISSING_VERIFICATION_REQUIREMENTS = [
    "Verify the WINDFOR generation unit from an authoritative source.",
    "Verify WINDFOR interval duration and generation semantics.",
    "Approve a comparison grain and alignment method for WINDFOR forecasts "
    "and FUELHH actuals.",
]


class UpstreamDataValidationError(ValueError):
    """Raised when retrieved rows cannot safely enter validated processing."""


def run_analysis(
    request: AnalysisRequest,
    *,
    client: ElexonClient,
) -> AnalysisResponse:
    """Fetch and validate both datasets, select forecasts, and block metrics.

    Actuals and forecasts are deliberately not joined. The documented
    interval-resolution difference and unverified WINDFOR semantics prevent a
    safe real-data accuracy calculation.
    """
    try:
        forecast_raw = client.fetch_windfor(
            publish_datetime_from=request.forecast_publish_from.isoformat(),
            publish_datetime_to=request.forecast_publish_to.isoformat(),
        )
        actual_raw = client.fetch_fuelhh(
            settlement_date_from=request.delivery_settlement_date_from.isoformat(),
            settlement_date_to=request.delivery_settlement_date_to.isoformat(),
        )
    except (TypeError, ValueError) as exc:
        if isinstance(exc, UpstreamDataValidationError):
            raise
        raise UpstreamDataValidationError(
            "An upstream response could not be validated."
        ) from exc

    forecast_report = validate_windfor(forecast_raw)
    actual_report = validate_fuelhh(actual_raw)

    decision_contexts = [
        DecisionContext(
            decision_date=item.decision_date,
            cutoff=item.cutoff,
        )
        for item in request.decision_cutoffs
    ]
    decision_window = DecisionDateWindow(
        request.decision_period_start,
        request.decision_period_end,
    )
    delivery_start_from = pd.Timestamp(
        request.delivery_start_from
    ).tz_convert("UTC")
    delivery_start_to = pd.Timestamp(
        request.delivery_start_to
    ).tz_convert("UTC")
    delivery_intervals = [
        record["startTimeUtc"]
        for record in forecast_report.records
        if delivery_start_from
        <= record["startTimeUtc"]
        < delivery_start_to
    ]
    try:
        selections = select_forecasts(
            forecast_report,
            decision_contexts=decision_contexts,
            delivery_intervals=delivery_intervals,
            decision_date_window=decision_window,
        )
    except ForecastSelectionInputError as exc:
        raise UpstreamDataValidationError(
            "Retrieved forecast data could not be used for selection."
        ) from exc

    selected_responses = [
        SelectedForecastResponse(
            decision_date=item.decision_date,
            delivery_interval=item.delivery_interval.to_pydatetime(),
            original_start_time=_optional_string(item.original_start_time),
            generation=item.generation,
            publish_time=(
                item.publish_time.to_pydatetime()
                if item.publish_time is not None
                else None
            ),
            original_publish_time=_optional_string(
                item.original_publish_time
            ),
            decision_cutoff=item.decision_cutoff.to_pydatetime(),
            status=item.status,
            rationale=item.rationale,
            eligible_record_count=item.eligible_record_count,
            duplicate_information=[
                DuplicateInfoResponse(
                    publish_time=duplicate.publish_time.to_pydatetime(),
                    kind=duplicate.kind,
                    record_count=duplicate.record_count,
                )
                for duplicate in item.duplicate_information
            ],
        )
        for item in selections
    ]

    return AnalysisResponse(
        status="metrics_blocked",
        decision_period_start=request.decision_period_start,
        decision_period_end=request.decision_period_end,
        delivery_start_from=request.delivery_start_from,
        delivery_start_to=request.delivery_start_to,
        delivery_settlement_date_from=request.delivery_settlement_date_from,
        delivery_settlement_date_to=request.delivery_settlement_date_to,
        forecast_publish_from=request.forecast_publish_from,
        forecast_publish_to=request.forecast_publish_to,
        metrics_status="comparability_unverified",
        metrics=None,
        metrics_block_reason=_metrics_block_reason(
            forecast_count=len(forecast_raw),
            actual_count=len(actual_raw),
            selection_count=len(selections),
        ),
        missing_verification_requirements=list(
            MISSING_VERIFICATION_REQUIREMENTS
        ),
        data_quality=DataQualityResponse(
            forecast_records_received=len(forecast_raw),
            forecast_records_validated=len(forecast_report.records),
            forecast_records_rejected=len(forecast_report.rejected),
            actual_records_received=len(actual_raw),
            actual_records_validated=len(actual_report.records),
            actual_records_rejected=len(actual_report.rejected),
            non_wind_records_excluded=len(actual_report.excluded),
            selection_count=len(selections),
            ambiguous_selection_count=sum(
                item.status == "ambiguous" for item in selections
            ),
        ),
        selected_forecasts=selected_responses,
    )


def _optional_string(value: object | None) -> str | None:
    return value if isinstance(value, str) else None


def _metrics_block_reason(
    *,
    forecast_count: int,
    actual_count: int,
    selection_count: int,
) -> str:
    reasons = [METRICS_BLOCK_REASON]
    if forecast_count == 0:
        reasons.append("No WINDFOR records were returned for the requested publication window.")
    if actual_count == 0:
        reasons.append(
            "No FUELHH records were returned for the requested settlement-date range."
        )
    if selection_count == 0:
        reasons.append(
            "No forecast delivery intervals were available in the requested "
            "delivery-start window."
        )
    return " ".join(reasons)
