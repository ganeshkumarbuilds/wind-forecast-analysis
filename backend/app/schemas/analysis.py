from datetime import date, datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class DecisionCutoffInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision_date: date
    cutoff: AwareDatetime


class AnalysisRequest(BaseModel):
    """Explicit decision, delivery-data, and forecast-publication scopes."""

    model_config = ConfigDict(extra="forbid")

    decision_period_start: date
    decision_period_end: date
    decision_cutoffs: list[DecisionCutoffInput] = Field(min_length=1)
    delivery_start_from: AwareDatetime
    delivery_start_to: AwareDatetime
    delivery_settlement_date_from: date
    delivery_settlement_date_to: date
    forecast_publish_from: AwareDatetime
    forecast_publish_to: AwareDatetime

    @model_validator(mode="after")
    def validate_periods(self) -> AnalysisRequest:
        january_start = date(2026, 1, 1)
        january_end = date(2026, 1, 31)

        if self.decision_period_start > self.decision_period_end:
            raise ValueError(
                "decision_period_start must not be after decision_period_end."
            )
        if (
            self.decision_period_start < january_start
            or self.decision_period_end > january_end
        ):
            raise ValueError(
                "The decision period must fall within January 2026."
            )
        if (
            self.delivery_settlement_date_from
            > self.delivery_settlement_date_to
        ):
            raise ValueError(
                "delivery_settlement_date_from must not be after "
                "delivery_settlement_date_to."
            )
        if self.delivery_start_from >= self.delivery_start_to:
            raise ValueError(
                "delivery_start_from must be earlier than delivery_start_to."
            )
        if self.forecast_publish_from > self.forecast_publish_to:
            raise ValueError(
                "forecast_publish_from must not be after forecast_publish_to."
            )

        for context in self.decision_cutoffs:
            if not (
                self.decision_period_start
                <= context.decision_date
                <= self.decision_period_end
            ):
                raise ValueError(
                    "Every decision cutoff date must fall within the "
                    "decision period."
                )
        if len(
            {
                (context.decision_date, context.cutoff)
                for context in self.decision_cutoffs
            }
        ) != len(self.decision_cutoffs):
            raise ValueError("Decision cutoff entries must be unique.")

        return self


class DuplicateInfoResponse(BaseModel):
    publish_time: datetime
    kind: Literal["exact", "conflicting"]
    record_count: int


class SelectedForecastResponse(BaseModel):
    decision_date: date
    delivery_interval: datetime
    original_start_time: str | None
    generation: int | float | None
    publish_time: datetime | None
    original_publish_time: str | None
    decision_cutoff: datetime
    status: Literal["selected", "no_eligible_forecast", "ambiguous"]
    rationale: str
    eligible_record_count: int
    duplicate_information: list[DuplicateInfoResponse]


class DataQualityResponse(BaseModel):
    forecast_records_received: int
    forecast_records_validated: int
    forecast_records_rejected: int
    actual_records_received: int
    actual_records_validated: int
    actual_records_rejected: int
    non_wind_records_excluded: int
    selection_count: int
    ambiguous_selection_count: int


class AnalysisResponse(BaseModel):
    status: Literal["metrics_blocked"]
    decision_period_start: date
    decision_period_end: date
    delivery_start_from: datetime
    delivery_start_to: datetime
    delivery_settlement_date_from: date
    delivery_settlement_date_to: date
    forecast_publish_from: datetime
    forecast_publish_to: datetime
    metrics_status: Literal["comparability_unverified"]
    metrics: None = None
    metrics_block_reason: str
    missing_verification_requirements: list[str]
    data_quality: DataQualityResponse
    selected_forecasts: list[SelectedForecastResponse]
