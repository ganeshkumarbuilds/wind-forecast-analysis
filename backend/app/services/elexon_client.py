from __future__ import annotations

import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Callable, Sequence

import httpx

BASE_URL = "https://data.elexon.co.uk/bmrs/api/v1"
FUELHH_PATH = "/datasets/FUELHH/stream"
WINDFOR_PATH = "/datasets/WINDFOR/stream"
FUELHH_REQUIRED_FIELDS = frozenset({"fuelType", "startTime", "generation"})
WINDFOR_REQUIRED_FIELDS = frozenset(
    {"startTime", "publishTime", "generation"}
)


class ElexonClientError(Exception):
    """Base class for Elexon client failures."""


class ElexonConnectionError(ElexonClientError):
    """The API request failed before an HTTP response was received."""


class ElexonTimeoutError(ElexonConnectionError):
    """The API request exceeded its configured timeout."""


class ElexonHTTPError(ElexonClientError):
    """The API returned an unsuccessful HTTP status."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code


class ElexonResponseError(ElexonClientError):
    """The API response was not valid JSON in the expected shape."""


class ElexonClient:
    """Small synchronous client for the documented FUELHH and WINDFOR APIs."""

    def __init__(
        self,
        *,
        base_url: str = BASE_URL,
        connect_timeout: float = 5.0,
        request_timeout: float = 30.0,
        max_retries: int = 2,
        backoff_factor: float = 0.5,
        max_retry_delay: float = 5.0,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if connect_timeout <= 0 or request_timeout <= 0:
            raise ValueError("Timeout values must be positive.")
        if max_retries < 0:
            raise ValueError("max_retries cannot be negative.")
        if backoff_factor < 0 or max_retry_delay < 0:
            raise ValueError("Retry delays cannot be negative.")

        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=httpx.Timeout(
                timeout=request_timeout,
                connect=connect_timeout,
            ),
            transport=transport,
        )
        self._max_retries = max_retries
        self._backoff_factor = backoff_factor
        self._max_retry_delay = max_retry_delay
        self._sleep = sleep

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> ElexonClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def fetch_fuelhh(
        self,
        *,
        settlement_date_from: str | None = None,
        settlement_date_to: str | None = None,
        publish_datetime_from: str | None = None,
        publish_datetime_to: str | None = None,
        settlement_period: int | Sequence[int] | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch FUELHH records, requesting and returning WIND records only."""
        if (
            settlement_date_from is not None
            or settlement_date_to is not None
        ) and (
            publish_datetime_from is not None
            or publish_datetime_to is not None
        ):
            raise ValueError(
                "FUELHH settlement-date and publication-time filters "
                "cannot be combined."
            )

        params: list[tuple[str, str]] = [("fuelType", "WIND")]
        self._append_param(params, "settlementDateFrom", settlement_date_from)
        self._append_param(params, "settlementDateTo", settlement_date_to)
        self._append_param(
            params, "publishDateTimeFrom", publish_datetime_from
        )
        self._append_param(params, "publishDateTimeTo", publish_datetime_to)
        if settlement_period is not None:
            periods = (
                [settlement_period]
                if isinstance(settlement_period, int)
                else settlement_period
            )
            params.extend(
                ("settlementPeriod", str(period)) for period in periods
            )

        records = self._fetch_records(
            FUELHH_PATH,
            params,
            FUELHH_REQUIRED_FIELDS,
            dataset_name="FUELHH",
        )
        return [record for record in records if record["fuelType"] == "WIND"]

    def fetch_windfor(
        self,
        *,
        publish_datetime_from: str | None = None,
        publish_datetime_to: str | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch WINDFOR records, retaining timestamp strings unchanged."""
        params: list[tuple[str, str]] = []
        self._append_param(
            params, "publishDateTimeFrom", publish_datetime_from
        )
        self._append_param(
            params, "publishDateTimeTo", publish_datetime_to
        )
        return self._fetch_records(
            WINDFOR_PATH,
            params,
            WINDFOR_REQUIRED_FIELDS,
            dataset_name="WINDFOR",
        )

    @staticmethod
    def _append_param(
        params: list[tuple[str, str]],
        name: str,
        value: str | None,
    ) -> None:
        if value is not None:
            params.append((name, value))

    def _fetch_records(
        self,
        path: str,
        params: list[tuple[str, str]],
        required_fields: frozenset[str],
        *,
        dataset_name: str,
    ) -> list[dict[str, Any]]:
        response = self._request(path, params)
        try:
            payload = response.json()
        except (ValueError, UnicodeDecodeError) as exc:
            raise ElexonResponseError(
                f"{dataset_name} response was not valid JSON."
            ) from exc

        if not isinstance(payload, list):
            raise ElexonResponseError(
                f"{dataset_name} response must be a JSON array."
            )

        records: list[dict[str, Any]] = []
        for index, item in enumerate(payload):
            if not isinstance(item, dict):
                raise ElexonResponseError(
                    f"{dataset_name} record at index {index} must be an object."
                )
            missing_fields = required_fields.difference(item)
            if missing_fields:
                missing = ", ".join(sorted(missing_fields))
                raise ElexonResponseError(
                    f"{dataset_name} record at index {index} is missing "
                    f"required fields: {missing}."
                )
            self._validate_record(item, index, dataset_name)
            records.append(item)
        return records

    @staticmethod
    def _validate_record(
        item: dict[str, Any],
        index: int,
        dataset_name: str,
    ) -> None:
        for field in ("startTime",):
            if not isinstance(item[field], str):
                raise ElexonResponseError(
                    f"{dataset_name} record at index {index} has an invalid "
                    f"{field}; expected a string."
                )

        if dataset_name == "WINDFOR" and not isinstance(
            item["publishTime"], str
        ):
            raise ElexonResponseError(
                f"WINDFOR record at index {index} has an invalid publishTime; "
                "expected a string."
            )
        if dataset_name == "FUELHH" and not isinstance(item["fuelType"], str):
            raise ElexonResponseError(
                f"FUELHH record at index {index} has an invalid fuelType; "
                "expected a string."
            )

        generation = item["generation"]
        if generation is not None and (
            isinstance(generation, bool) or not isinstance(generation, int)
        ):
            raise ElexonResponseError(
                f"{dataset_name} record at index {index} has an invalid "
                "generation; expected an integer or null."
            )

    def _request(
        self,
        path: str,
        params: list[tuple[str, str]],
    ) -> httpx.Response:
        for attempt in range(self._max_retries + 1):
            try:
                response = self._client.get(path, params=params)
            except httpx.TimeoutException as exc:
                raise ElexonTimeoutError(
                    f"Request to {path} timed out."
                ) from exc
            except httpx.RequestError as exc:
                raise ElexonConnectionError(
                    f"Request to {path} failed: {exc}."
                ) from exc

            if response.status_code == 429 or response.status_code >= 500:
                if attempt < self._max_retries:
                    delay = self._retry_delay(response, attempt)
                    self._sleep(delay)
                    continue

            if response.is_error:
                raise ElexonHTTPError(
                    response.status_code,
                    f"Elexon API returned HTTP {response.status_code} "
                    f"for {path}.",
                )
            return response

        raise RuntimeError("Retry loop exited without a response.")

    def _retry_delay(
        self,
        response: httpx.Response,
        attempt: int,
    ) -> float:
        retry_after = self._parse_retry_after(response.headers.get("Retry-After"))
        if retry_after is not None:
            return min(retry_after, self._max_retry_delay)
        exponential_delay = self._backoff_factor * (2**attempt)
        return min(exponential_delay, self._max_retry_delay)

    @staticmethod
    def _parse_retry_after(value: str | None) -> float | None:
        if value is None:
            return None
        try:
            return max(0.0, float(value))
        except ValueError:
            try:
                retry_at = parsedate_to_datetime(value)
                if retry_at.tzinfo is None:
                    retry_at = retry_at.replace(tzinfo=timezone.utc)
                return max(
                    0.0,
                    (retry_at - datetime.now(timezone.utc)).total_seconds(),
                )
            except (TypeError, ValueError, OverflowError):
                return None
