import { describe, expect, it, vi } from "vitest";
import { submitAnalysis, type AnalysisRequestPayload } from "./api";

const payload: AnalysisRequestPayload = {
  decision_period_start: "2026-01-01",
  decision_period_end: "2026-01-31",
  decision_cutoffs: [
    {
      decision_date: "2026-01-15",
      cutoff: "2026-01-15T12:00:00Z",
    },
  ],
  delivery_start_from: "2026-01-16T00:00:00Z",
  delivery_start_to: "2026-01-17T00:00:00Z",
  delivery_settlement_date_from: "2026-01-16",
  delivery_settlement_date_to: "2026-01-16",
  forecast_publish_from: "2025-12-28T00:00:00Z",
  forecast_publish_to: "2026-01-16T12:00:00Z",
};

describe("analysis API client", () => {
  it("posts the backend request schema unchanged", async () => {
    const responseBody = { status: "metrics_blocked", metrics: null };
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(
        new Response(JSON.stringify(responseBody), { status: 200 }),
      );

    await expect(submitAnalysis(payload)).resolves.toEqual(responseBody);
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringMatching(/\/api\/v1\/analysis$/),
      expect.objectContaining({
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      }),
    );
  });

  it("surfaces the safe API error message", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          code: "http_502",
          message: "The Elexon API request failed or returned invalid data.",
        }),
        { status: 502 },
      ),
    );

    await expect(submitAnalysis(payload)).rejects.toThrow(
      "The Elexon API request failed or returned invalid data.",
    );
  });
});
