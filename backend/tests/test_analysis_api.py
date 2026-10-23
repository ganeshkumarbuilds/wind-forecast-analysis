"""Mocked API tests; all Elexon records in this file are synthetic fixtures."""

from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.analysis import get_elexon_client
from app.main import app
from app.services.elexon_client import ElexonClient


def analysis_payload(**overrides: object) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "decision_period_start": "2026-01-01",
        "decision_period_end": "2026-01-31",
        "decision_cutoffs": [
            {
                "decision_date": "2026-01-31",
                "cutoff": "2026-01-31T22:00:00Z",
            }
        ],
        "delivery_start_from": "2026-02-01T00:00:00Z",
        "delivery_start_to": "2026-02-03T00:00:00Z",
        "delivery_settlement_date_from": "2026-02-01",
        "delivery_settlement_date_to": "2026-02-01",
        "forecast_publish_from": "2026-01-01T00:00:00Z",
        "forecast_publish_to": "2026-02-01T00:00:00Z",
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def api_client_factory() -> Iterator[Any]:
    created_clients: list[ElexonClient] = []

    def request(
        forecast_rows: list[dict[str, Any]] | None = None,
        actual_rows: list[dict[str, Any]] | None = None,
        *,
        forecast_status: int = 200,
        actual_status: int = 200,
    ) -> tuple[TestClient, list[httpx.Request]]:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if request.url.path.endswith("/datasets/WINDFOR/stream"):
                if forecast_status != 200:
                    return httpx.Response(forecast_status, json={"error": "synthetic"})
                return httpx.Response(200, json=forecast_rows or [])
            if request.url.path.endswith("/datasets/FUELHH/stream"):
                if actual_status != 200:
                    return httpx.Response(actual_status, json={"error": "synthetic"})
                return httpx.Response(200, json=actual_rows or [])
            return httpx.Response(404)

        client = ElexonClient(
            transport=httpx.MockTransport(handler),
            max_retries=0,
        )
        created_clients.append(client)

        def override_client() -> Iterator[ElexonClient]:
            yield client

        app.dependency_overrides[get_elexon_client] = override_client
        return TestClient(app), requests

    try:
        yield request
    finally:
        app.dependency_overrides.clear()
        for client in created_clients:
            client.close()


def test_success_returns_blocked_metrics_with_selected_forecasts(
    api_client_factory: Any,
) -> None:
    client, _ = api_client_factory(
        forecast_rows=[
            {
                "dataset": "WINDFOR",
                "startTime": "2026-02-01T00:00:00Z",
                "publishTime": "2026-01-31T21:30:00Z",
                "generation": 7200,
            },
            {
                "dataset": "WINDFOR",
                "startTime": "2026-02-01T00:00:00Z",
                "publishTime": "2026-01-31T22:00:00Z",
                "generation": 9999,
            },
        ],
        actual_rows=[
            {
                "dataset": "FUELHH",
                "fuelType": "WIND",
                "startTime": "2026-02-01T00:00:00Z",
                "generation": 7000,
            }
        ],
    )

    response = client.post("/api/v1/analysis", json=analysis_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "metrics_blocked"
    assert body["metrics_status"] == "comparability_unverified"
    assert body["metrics"] is None
    assert body["data_quality"]["actual_records_validated"] == 1
    assert body["selected_forecasts"][0]["generation"] == 7200
    assert body["selected_forecasts"][0]["publish_time"] == (
        "2026-01-31T21:30:00Z"
    )
    assert "units" in body["metrics_block_reason"]
    assert body["missing_verification_requirements"]


def test_january_decision_period_is_separate_from_february_delivery(
    api_client_factory: Any,
) -> None:
    client, requests = api_client_factory(
        forecast_rows=[
            {
                "dataset": "WINDFOR",
                "startTime": "2026-02-02T00:00:00Z",
                "publishTime": "2026-01-31T21:00:00Z",
                "generation": 8100,
            }
        ],
        actual_rows=[
            {
                "dataset": "FUELHH",
                "fuelType": "WIND",
                "startTime": "2026-02-01T23:30:00Z",
                "generation": 7900,
            }
        ],
    )

    response = client.post(
        "/api/v1/analysis",
        json=analysis_payload(
            delivery_settlement_date_from="2026-02-01",
            delivery_settlement_date_to="2026-02-02",
        ),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["decision_period_start"] == "2026-01-01"
    assert body["decision_period_end"] == "2026-01-31"
    assert body["delivery_start_from"] == "2026-02-01T00:00:00Z"
    assert body["delivery_start_to"] == "2026-02-03T00:00:00Z"
    assert body["delivery_settlement_date_from"] == "2026-02-01"
    assert body["selected_forecasts"][0]["decision_date"] == "2026-01-31"
    assert body["selected_forecasts"][0]["delivery_interval"] == (
        "2026-02-02T00:00:00Z"
    )
    actual_request = next(
        request
        for request in requests
        if request.url.path.endswith("/datasets/FUELHH/stream")
    )
    assert actual_request.url.params["settlementDateFrom"] == "2026-02-01"
    assert actual_request.url.params["settlementDateTo"] == "2026-02-02"


def test_forecasts_after_and_exactly_at_cutoff_are_not_selected(
    api_client_factory: Any,
) -> None:
    client, _ = api_client_factory(
        forecast_rows=[
            {
                "startTime": "2026-02-01T00:00:00Z",
                "publishTime": "2026-01-31T21:59:59Z",
                "generation": 7000,
            },
            {
                "startTime": "2026-02-01T00:00:00Z",
                "publishTime": "2026-01-31T22:00:00Z",
                "generation": 8000,
            },
            {
                "startTime": "2026-02-01T00:00:00Z",
                "publishTime": "2026-01-31T22:00:01Z",
                "generation": 9000,
            },
        ],
        actual_rows=[],
    )

    response = client.post("/api/v1/analysis", json=analysis_payload())

    selection = response.json()["selected_forecasts"][0]
    assert selection["status"] == "selected"
    assert selection["generation"] == 7000
    assert selection["eligible_record_count"] == 1


def test_original_forecast_timestamps_are_preserved(
    api_client_factory: Any,
) -> None:
    original_start = "2026-02-01T01:00:00+01:00"
    original_publish = "2026-01-31T22:30:00+01:00"
    client, _ = api_client_factory(
        forecast_rows=[
            {
                "startTime": original_start,
                "publishTime": original_publish,
                "generation": 5000,
            }
        ],
        actual_rows=[],
    )

    response = client.post("/api/v1/analysis", json=analysis_payload())

    selection = response.json()["selected_forecasts"][0]
    assert selection["original_start_time"] == original_start
    assert selection["original_publish_time"] == original_publish
    assert selection["delivery_interval"] == "2026-02-01T00:00:00Z"
    assert selection["publish_time"] == "2026-01-31T21:30:00Z"


def test_empty_upstream_data_returns_blocked_metrics_not_fabricated_results(
    api_client_factory: Any,
) -> None:
    client, _ = api_client_factory(forecast_rows=[], actual_rows=[])

    response = client.post("/api/v1/analysis", json=analysis_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "metrics_blocked"
    assert body["metrics"] is None
    assert body["selected_forecasts"] == []
    assert body["data_quality"]["forecast_records_received"] == 0
    assert body["data_quality"]["actual_records_received"] == 0


def test_missing_forecasts_are_reported_even_when_actuals_exist(
    api_client_factory: Any,
) -> None:
    client, _ = api_client_factory(
        forecast_rows=[],
        actual_rows=[
            {
                "fuelType": "WIND",
                "startTime": "2026-02-01T00:00:00Z",
                "generation": 7000,
            }
        ],
    )

    response = client.post("/api/v1/analysis", json=analysis_payload())

    body = response.json()
    assert response.status_code == 200
    assert body["metrics"] is None
    assert body["data_quality"]["actual_records_validated"] == 1
    assert body["data_quality"]["forecast_records_received"] == 0
    assert "No WINDFOR records" in body["metrics_block_reason"]


def test_missing_actuals_are_reported_even_when_forecasts_exist(
    api_client_factory: Any,
) -> None:
    client, _ = api_client_factory(
        forecast_rows=[
            {
                "startTime": "2026-02-01T00:00:00Z",
                "publishTime": "2026-01-31T21:00:00Z",
                "generation": 7000,
            }
        ],
        actual_rows=[],
    )

    response = client.post("/api/v1/analysis", json=analysis_payload())

    body = response.json()
    assert response.status_code == 200
    assert body["metrics"] is None
    assert body["data_quality"]["forecast_records_validated"] == 1
    assert body["data_quality"]["actual_records_received"] == 0
    assert "No FUELHH records" in body["metrics_block_reason"]


def test_records_outside_delivery_window_are_not_selected(
    api_client_factory: Any,
) -> None:
    client, _ = api_client_factory(
        forecast_rows=[
            {
                "startTime": "2026-02-04T00:00:00Z",
                "publishTime": "2026-01-31T21:00:00Z",
                "generation": 7000,
            }
        ],
        actual_rows=[],
    )

    response = client.post("/api/v1/analysis", json=analysis_payload())

    body = response.json()
    assert response.status_code == 200
    assert body["selected_forecasts"] == []
    assert "No forecast delivery intervals" in body["metrics_block_reason"]


def test_invalid_upstream_rows_are_counted_not_silently_used(
    api_client_factory: Any,
) -> None:
    client, _ = api_client_factory(
        forecast_rows=[
            {
                "startTime": "2026-02-01T00:00:00Z",
                "publishTime": "2026-01-31T21:00:00Z",
                "generation": None,
            }
        ],
        actual_rows=[],
    )

    response = client.post("/api/v1/analysis", json=analysis_payload())

    body = response.json()
    assert response.status_code == 200
    assert body["data_quality"]["forecast_records_received"] == 1
    assert body["data_quality"]["forecast_records_validated"] == 0
    assert body["data_quality"]["forecast_records_rejected"] == 1
    assert body["selected_forecasts"] == []
    assert body["metrics"] is None


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        (
            {
                "decision_period_start": "not-a-date",
            },
            "decision_period_start",
        ),
        (
            {
                "decision_period_start": "2026-01-20",
                "decision_period_end": "2026-01-10",
            },
            "decision_period_start",
        ),
        (
            {
                "delivery_settlement_date_from": "2026-02-10",
                "delivery_settlement_date_to": "2026-02-01",
            },
            "delivery_settlement_date_from",
        ),
        (
            {
                "delivery_start_from": "2026-02-02T00:00:00Z",
                "delivery_start_to": "2026-02-01T00:00:00Z",
            },
            "delivery_start_from",
        ),
        (
            {
                "decision_cutoffs": [
                    {
                        "decision_date": "2026-01-31",
                        "cutoff": "2026-01-31T22:00:00",
                    }
                ]
            },
            "cutoff",
        ),
    ],
)
def test_invalid_or_reversed_ranges_return_validation_error(
    api_client_factory: Any,
    overrides: dict[str, object],
    message: str,
) -> None:
    client, requests = api_client_factory()

    response = client.post(
        "/api/v1/analysis",
        json=analysis_payload(**overrides),
    )

    assert response.status_code == 422
    assert message.lower() in response.text.lower()
    assert requests == []


def test_out_of_period_cutoff_date_is_rejected(
    api_client_factory: Any,
) -> None:
    client, requests = api_client_factory()

    response = client.post(
        "/api/v1/analysis",
        json=analysis_payload(
            decision_cutoffs=[
                {
                    "decision_date": "2026-02-01",
                    "cutoff": "2026-02-01T12:00:00Z",
                }
            ]
        ),
    )

    assert response.status_code == 422
    assert requests == []


def test_upstream_http_failure_returns_safe_error(
    api_client_factory: Any,
) -> None:
    client, _ = api_client_factory(forecast_status=400)

    response = client.post("/api/v1/analysis", json=analysis_payload())

    assert response.status_code == 502
    assert response.json() == {
        "code": "http_502",
        "message": "The Elexon API request failed or returned invalid data.",
    }
    assert "synthetic" not in response.text
    assert "Traceback" not in response.text


def test_no_real_metrics_are_computed_when_comparability_is_unverified(
    api_client_factory: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import metrics

    def fail_if_called(*args: object, **kwargs: object) -> None:
        raise AssertionError("Metrics must not run on unverified real data.")

    monkeypatch.setattr(metrics, "calculate_metrics", fail_if_called)
    client, _ = api_client_factory(
        forecast_rows=[
            {
                "startTime": "2026-02-01T00:00:00Z",
                "publishTime": "2026-01-31T21:00:00Z",
                "generation": 7000,
            }
        ],
        actual_rows=[
            {
                "fuelType": "WIND",
                "startTime": "2026-02-01T00:00:00Z",
                "generation": 6900,
            }
        ],
    )

    response = client.post("/api/v1/analysis", json=analysis_payload())

    assert response.status_code == 200
    assert response.json()["metrics"] is None
    assert response.json()["metrics_status"] == "comparability_unverified"
