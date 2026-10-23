export type HealthResponse = {
  status: string;
};

export type DuplicateInfo = {
  publish_time: string;
  kind: "exact" | "conflicting";
  record_count: number;
};

export type SelectedForecast = {
  decision_date: string;
  delivery_interval: string;
  original_start_time: string | null;
  generation: number | null;
  publish_time: string | null;
  original_publish_time: string | null;
  decision_cutoff: string;
  status: "selected" | "no_eligible_forecast" | "ambiguous";
  rationale: string;
  eligible_record_count: number;
  duplicate_information: DuplicateInfo[];
};

export type AnalysisResponse = {
  status: "metrics_blocked";
  decision_period_start: string;
  decision_period_end: string;
  delivery_start_from: string;
  delivery_start_to: string;
  delivery_settlement_date_from: string;
  delivery_settlement_date_to: string;
  forecast_publish_from: string;
  forecast_publish_to: string;
  metrics_status: "comparability_unverified";
  metrics: null;
  metrics_block_reason: string;
  missing_verification_requirements: string[];
  data_quality: {
    forecast_records_received: number;
    forecast_records_validated: number;
    forecast_records_rejected: number;
    actual_records_received: number;
    actual_records_validated: number;
    actual_records_rejected: number;
    non_wind_records_excluded: number;
    selection_count: number;
    ambiguous_selection_count: number;
  };
  selected_forecasts: SelectedForecast[];
};

const configuredBaseUrl = import.meta.env.VITE_API_BASE_URL;
export const apiBaseUrl = (
  configuredBaseUrl?.trim() || ""
).replace(/\/+$/, "");

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${apiBaseUrl}${path}`, init);
  } catch {
    throw new Error(
      "Could not reach the WindScope API. Check that the backend is running and the API URL is correct.",
    );
  }

  let body: unknown;
  try {
    body = await response.json();
  } catch {
    throw new Error("The API returned an unreadable response.");
  }

  if (!response.ok) {
    const message = getErrorMessage(body) ??
      `The API request failed (HTTP ${response.status}).`;
    throw new Error(message);
  }

  return body as T;
}

function getErrorMessage(body: unknown): string | undefined {
  if (typeof body !== "object" || body === null || !("message" in body)) {
    return undefined;
  }
  return typeof body.message === "string" ? body.message : undefined;
}

export function fetchHealth(): Promise<HealthResponse> {
  return requestJson<HealthResponse>("/api/v1/health");
}

export function submitAnalysis(
  payload: AnalysisRequestPayload,
): Promise<AnalysisResponse> {
  return requestJson<AnalysisResponse>("/api/v1/analysis", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export type AnalysisRequestPayload = {
  decision_period_start: string;
  decision_period_end: string;
  decision_cutoffs: { decision_date: string; cutoff: string }[];
  delivery_start_from: string;
  delivery_start_to: string;
  delivery_settlement_date_from: string;
  delivery_settlement_date_to: string;
  forecast_publish_from: string;
  forecast_publish_to: string;
};
