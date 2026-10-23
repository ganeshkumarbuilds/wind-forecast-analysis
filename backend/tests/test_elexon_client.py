from typing import Any

import httpx
import pytest

from app.services.elexon_client import (
    BASE_URL,
    ElexonClient,
    ElexonConnectionError,
    ElexonHTTPError,
    ElexonResponseError,
    ElexonTimeoutError,
)


def make_client(
    handler: Any,
    *,
    sleeps: list[float] | None = None,
    max_retries: int = 2,
    max_retry_delay: float = 1.0,
) -> ElexonClient:
    return ElexonClient(
        transport=httpx.MockTransport(handler),
        max_retries=max_retries,
        backoff_factor=0.25,
        max_retry_delay=max_retry_delay,
        sleep=(sleeps if sleeps is not None else []).append,
    )


def test_fetch_fuelhh_requests_and_returns_only_wind_records() -> None:
    requested: list[httpx.Request] = []
    payload = [
        {
            "fuelType": "WIND",
            "startTime": "2026-01-01T00:00:00Z",
            "generation": 1200,
        },
        {
            "fuelType": "GAS",
            "startTime": "2026-01-01T00:00:00Z",
            "generation": 900,
        },
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(request)
        return httpx.Response(200, json=payload)

    with make_client(handler) as client:
        records = client.fetch_fuelhh(
            settlement_date_from="2026-01-01",
            settlement_date_to="2026-01-31",
            settlement_period=[1, 2],
        )

    assert len(requested) == 1
    request = requested[0]
    assert request.method == "GET"
    assert request.url == httpx.URL(
        BASE_URL
        + "/datasets/FUELHH/stream?fuelType=WIND"
        "&settlementDateFrom=2026-01-01"
        "&settlementDateTo=2026-01-31"
        "&settlementPeriod=1"
        "&settlementPeriod=2"
    )
    assert [record["fuelType"] for record in records] == ["WIND"]


def test_fetch_windfor_preserves_timestamp_strings_and_documented_params() -> None:
    requested: list[httpx.Request] = []
    timestamps = {
        "startTime": "2026-01-01T00:00:00.000+00:00",
        "publishTime": "2026-01-01T00:05:00.123Z",
        "generation": 12345,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(request)
        return httpx.Response(200, json=[timestamps])

    with make_client(handler) as client:
        records = client.fetch_windfor(
            publish_datetime_from="2026-01-01T00:00:00Z",
            publish_datetime_to="2026-02-01T00:00:00Z",
        )

    assert records == [timestamps]
    assert records[0]["publishTime"] == timestamps["publishTime"]
    assert records[0]["startTime"] == timestamps["startTime"]
    assert set(dict(requested[0].url.params)) == {
        "publishDateTimeFrom",
        "publishDateTimeTo",
    }
    assert requested[0].url.path == "/bmrs/api/v1/datasets/WINDFOR/stream"


def test_fuelhh_rejects_combined_settlement_and_publication_filters() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("Invalid filters must be rejected before request.")

    with make_client(handler) as client:
        with pytest.raises(ValueError, match="cannot be combined"):
            client.fetch_fuelhh(
                settlement_date_from="2026-01-01",
                publish_datetime_from="2026-01-01T00:00:00Z",
            )


def test_http_400_is_not_retried() -> None:
    requests = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal requests
        requests += 1
        return httpx.Response(400, text="invalid query")

    with make_client(handler) as client:
        with pytest.raises(ElexonHTTPError) as error:
            client.fetch_windfor()

    assert error.value.status_code == 400
    assert requests == 1


def test_http_429_retries_and_caps_retry_after_delay() -> None:
    requests = 0
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal requests
        requests += 1
        if requests == 1:
            return httpx.Response(429, headers={"Retry-After": "10"})
        return httpx.Response(200, json=[])

    with make_client(
        handler,
        sleeps=sleeps,
        max_retries=2,
        max_retry_delay=0.5,
    ) as client:
        assert client.fetch_windfor() == []

    assert requests == 2
    assert sleeps == [0.5]


def test_server_errors_are_retried_only_up_to_configured_bound() -> None:
    requests = 0
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal requests
        requests += 1
        return httpx.Response(503, text="unavailable")

    with make_client(
        handler,
        sleeps=sleeps,
        max_retries=2,
    ) as client:
        with pytest.raises(ElexonHTTPError) as error:
            client.fetch_windfor()

    assert error.value.status_code == 503
    assert requests == 3
    assert sleeps == [0.25, 0.5]


def test_timeout_is_reported_explicitly() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    with make_client(handler) as client:
        with pytest.raises(ElexonTimeoutError):
            client.fetch_windfor()


def test_connection_failure_is_reported_explicitly() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    with make_client(handler) as client:
        with pytest.raises(ElexonConnectionError):
            client.fetch_windfor()


def test_malformed_json_is_reported() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"{not-json")

    with make_client(handler) as client:
        with pytest.raises(ElexonResponseError, match="valid JSON"):
            client.fetch_windfor()


@pytest.mark.parametrize(
    "payload",
    [
        {"records": []},
        ["not a record"],
        [{"startTime": "2026-01-01T00:00:00Z"}],
    ],
)
def test_unexpected_response_structure_is_reported(payload: Any) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    with make_client(handler) as client:
        with pytest.raises(ElexonResponseError):
            client.fetch_windfor()


def test_fuelhh_rejects_malformed_record_instead_of_dropping_it() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[
                {
                    "fuelType": "WIND",
                    "startTime": "2026-01-01T00:00:00Z",
                    "generation": "not-an-integer",
                }
            ],
        )

    with make_client(handler) as client:
        with pytest.raises(ElexonResponseError, match="generation"):
            client.fetch_fuelhh()
