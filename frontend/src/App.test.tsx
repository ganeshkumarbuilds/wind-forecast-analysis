import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";

const blockedResponse = {
  status: "metrics_blocked" as const,
  decision_period_start: "2026-01-01",
  decision_period_end: "2026-01-31",
  delivery_start_from: "2026-02-01T00:00:00Z",
  delivery_start_to: "2026-02-02T00:00:00Z",
  delivery_settlement_date_from: "2026-02-01",
  delivery_settlement_date_to: "2026-02-01",
  forecast_publish_from: "2026-01-01T00:00:00Z",
  forecast_publish_to: "2026-02-01T00:00:00Z",
  metrics_status: "comparability_unverified" as const,
  metrics: null,
  metrics_block_reason:
    "Metrics are blocked because units and interval semantics are unverified.",
  missing_verification_requirements: ["Verify forecast interval semantics."],
  data_quality: {
    forecast_records_received: 1,
    forecast_records_validated: 1,
    forecast_records_rejected: 0,
    actual_records_received: 1,
    actual_records_validated: 1,
    actual_records_rejected: 0,
    non_wind_records_excluded: 0,
    selection_count: 1,
    ambiguous_selection_count: 0,
  },
  selected_forecasts: [
    {
      decision_date: "2026-01-31",
      delivery_interval: "2026-02-01T00:00:00Z",
      original_start_time: "2026-02-01T00:00:00Z",
      generation: 7200,
      publish_time: "2026-01-31T21:30:00Z",
      original_publish_time: "2026-01-31T21:30:00Z",
      decision_cutoff: "2026-01-31T22:00:00Z",
      status: "selected" as const,
      rationale: "Latest eligible forecast.",
      eligible_record_count: 1,
      duplicate_information: [],
    },
  ],
};

describe("WindScope dashboard", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("reports that the health endpoint only confirms the API process", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ status: "ok" }), { status: 200 }),
    );

    render(<App />);

    expect(await screen.findByText("API process online")).toBeInTheDocument();
    expect(
      screen.getByText(/No forecast or actual records have been loaded yet/),
    ).toBeInTheDocument();
  });

  it("submits explicit UTC bounds and renders a blocked-metrics response", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ status: "ok" }), { status: 200 }),
    );
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify(blockedResponse), { status: 200 }),
    );

    render(<App />);
    fireEvent.change(screen.getByLabelText("Decision date"), {
      target: { value: "2026-01-31" },
    });
    fireEvent.change(screen.getByLabelText("Decision cutoff time (UTC)"), {
      target: { value: "22:00" },
    });
    fireEvent.change(screen.getByLabelText("Delivery start from (UTC)"), {
      target: { value: "2026-02-01T00:00" },
    });
    fireEvent.change(
      screen.getByLabelText("Delivery start to (UTC, exclusive)"),
      { target: { value: "2026-02-02T00:00" } },
    );
    fireEvent.change(screen.getByLabelText("Actual settlement date from"), {
      target: { value: "2026-02-01" },
    });
    fireEvent.change(screen.getByLabelText("Actual settlement date to"), {
      target: { value: "2026-02-01" },
    });
    fireEvent.change(screen.getByLabelText("Published from (UTC)"), {
      target: { value: "2026-01-01T00:00" },
    });
    fireEvent.change(screen.getByLabelText("Published to (UTC)"), {
      target: { value: "2026-02-01T00:00" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Run analysis/ }));

    expect(
      await screen.findByText("Selected publications"),
    ).toBeInTheDocument();
    expect(
      screen.getAllByText(/Metrics are blocked because units and interval/)[0],
    ).toBeInTheDocument();
    expect(
      screen.getAllByText("2026-02-01T00:00:00Z"),
    ).toHaveLength(2);
    expect(screen.queryByText(/MAE|RMSE|MAPE/)).not.toBeInTheDocument();

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const [, request] = fetchMock.mock.calls[1];
    expect(JSON.parse(String(request?.body))).toMatchObject({
      decision_period_start: "2026-01-01",
      decision_period_end: "2026-01-31",
      decision_cutoffs: [
        {
          decision_date: "2026-01-31",
          cutoff: "2026-01-31T22:00:00Z",
        },
      ],
      delivery_start_from: "2026-02-01T00:00:00Z",
      delivery_start_to: "2026-02-02T00:00:00Z",
      delivery_settlement_date_from: "2026-02-01",
      delivery_settlement_date_to: "2026-02-01",
    });
  });

  it("shows an understandable empty state for no matching selections", async () => {
    const noSelections = {
      ...blockedResponse,
      selected_forecasts: [],
      data_quality: {
        ...blockedResponse.data_quality,
        forecast_records_received: 0,
        forecast_records_validated: 0,
        actual_records_received: 0,
        actual_records_validated: 0,
        selection_count: 0,
      },
    };
    const fetchMock = vi.spyOn(globalThis, "fetch");
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ status: "ok" }), { status: 200 }),
    );
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify(noSelections), { status: 200 }),
    );

    render(<App />);
    fireEvent.change(screen.getByLabelText("Decision date"), {
      target: { value: "2026-01-31" },
    });
    fireEvent.change(screen.getByLabelText("Decision cutoff time (UTC)"), {
      target: { value: "22:00" },
    });
    fireEvent.change(screen.getByLabelText("Delivery start from (UTC)"), {
      target: { value: "2026-02-01T00:00" },
    });
    fireEvent.change(screen.getByLabelText("Delivery start to (UTC, exclusive)"), {
      target: { value: "2026-02-02T00:00" },
    });
    fireEvent.change(screen.getByLabelText("Actual settlement date from"), {
      target: { value: "2026-02-01" },
    });
    fireEvent.change(screen.getByLabelText("Actual settlement date to"), {
      target: { value: "2026-02-01" },
    });
    fireEvent.change(screen.getByLabelText("Published from (UTC)"), {
      target: { value: "2026-01-01T00:00" },
    });
    fireEvent.change(screen.getByLabelText("Published to (UTC)"), {
      target: { value: "2026-02-01T00:00" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Run analysis/ }));

    expect(
      await screen.findByText("No selected forecasts in this scope"),
    ).toBeInTheDocument();
  });
});
