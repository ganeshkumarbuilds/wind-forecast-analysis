import { useEffect, useState, type FormEvent } from "react";
import {
  apiBaseUrl,
  fetchHealth,
  submitAnalysis,
  type AnalysisRequestPayload,
  type AnalysisResponse,
  type SelectedForecast,
} from "./api";

type FormValues = {
  decisionPeriodStart: string;
  decisionPeriodEnd: string;
  decisionDate: string;
  cutoffTime: string;
  deliveryStartFrom: string;
  deliveryStartTo: string;
  settlementDateFrom: string;
  settlementDateTo: string;
  forecastPublishFrom: string;
  forecastPublishTo: string;
};

const initialForm: FormValues = {
  decisionPeriodStart: "2026-01-01",
  decisionPeriodEnd: "2026-01-31",
  decisionDate: "",
  cutoffTime: "",
  deliveryStartFrom: "",
  deliveryStartTo: "",
  settlementDateFrom: "",
  settlementDateTo: "",
  forecastPublishFrom: "",
  forecastPublishTo: "",
};

function utcTimestamp(value: string): string {
  return `${value}:00Z`;
}

function timestampLabel(value: string | null): string {
  return value ?? "Not available";
}

function App() {
  const [form, setForm] = useState<FormValues>(initialForm);
  const [health, setHealth] = useState<"checking" | "online" | "offline">(
    "checking",
  );
  const [analysis, setAnalysis] = useState<AnalysisResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let active = true;
    fetchHealth()
      .then((result) => {
        if (active) setHealth(result.status === "ok" ? "online" : "offline");
      })
      .catch(() => {
        if (active) setHealth("offline");
      });
    return () => {
      active = false;
    };
  }, []);

  function update<K extends keyof FormValues>(key: K, value: FormValues[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    setAnalysis(null);

    const payload: AnalysisRequestPayload = {
      decision_period_start: form.decisionPeriodStart,
      decision_period_end: form.decisionPeriodEnd,
      decision_cutoffs: [
        {
          decision_date: form.decisionDate,
          cutoff: `${form.decisionDate}T${form.cutoffTime}:00Z`,
        },
      ],
      delivery_start_from: utcTimestamp(form.deliveryStartFrom),
      delivery_start_to: utcTimestamp(form.deliveryStartTo),
      delivery_settlement_date_from: form.settlementDateFrom,
      delivery_settlement_date_to: form.settlementDateTo,
      forecast_publish_from: utcTimestamp(form.forecastPublishFrom),
      forecast_publish_to: utcTimestamp(form.forecastPublishTo),
    };

    try {
      setAnalysis(await submitAnalysis(payload));
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "The analysis request failed.",
      );
    } finally {
      setLoading(false);
    }
  }

  const canSubmit =
    !loading &&
    form.decisionPeriodStart !== "" &&
    form.decisionPeriodEnd !== "" &&
    form.decisionDate !== "" &&
    form.cutoffTime !== "" &&
    form.deliveryStartFrom !== "" &&
    form.deliveryStartTo !== "" &&
    form.settlementDateFrom !== "" &&
    form.settlementDateTo !== "" &&
    form.forecastPublishFrom !== "" &&
    form.forecastPublishTo !== "";

  return (
    <main className="app-shell">
      <header className="topbar">
        <a className="brand" href="/" aria-label="WindScope home">
          <span className="brand-mark" aria-hidden="true">
            <span />
            <span />
            <span />
          </span>
          <span>WindScope</span>
        </a>
        <div
          className={`api-indicator api-${health}`}
          role="status"
          aria-live="polite"
        >
          <span className="status-dot" />
          {health === "checking"
            ? "Checking API"
            : health === "online"
              ? "API process online"
              : "API unavailable"}
        </div>
      </header>

      <section className="hero">
        <div className="hero-copy">
          <p className="eyebrow">UK WIND · DAY-AHEAD ANALYSIS</p>
          <h1>See what was known<br />before the decision.</h1>
          <p className="hero-description">
            Review historical wind forecasts against explicit purchasing
            decision cutoffs. Forecast accuracy remains unavailable until
            forecast and actual data are verified as comparable.
          </p>
        </div>
        <div className="hero-stamp" aria-label="January 2026 assessment">
          <span>ASSESSMENT WINDOW</span>
          <strong>JAN ’26</strong>
          <span>DECISION COHORT</span>
        </div>
      </section>

      <section className="source-strip" aria-label="Analysis data sources">
        <div className="source-heading">
          <span className="source-icon actual-icon">A</span>
          <div>
            <span className="field-label">ACTUAL GENERATION</span>
            <strong>Elexon FUELHH</strong>
          </div>
          <span className="source-detail">Wind · half-hourly</span>
        </div>
        <div className="source-divider" aria-hidden="true" />
        <div className="source-heading">
          <span className="source-icon forecast-icon">F</span>
          <div>
            <span className="field-label">PUBLISHED FORECASTS</span>
            <strong>Elexon WINDFOR</strong>
          </div>
          <span className="source-detail">Historical publications</span>
        </div>
        <p className="source-note">
          Forecast units and interval semantics are not yet verified.
        </p>
      </section>

      <div className="workspace">
        <section className="panel controls-panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">ANALYSIS SCOPE</p>
              <h2>Define your request</h2>
            </div>
            <span className="step-number">01</span>
          </div>
          <form onSubmit={handleSubmit}>
            <fieldset>
              <legend>Decision period · January 2026</legend>
              <div className="form-grid two-columns">
                <DateField
                  id="decision-period-start"
                  label="Period start"
                  value={form.decisionPeriodStart}
                  januaryOnly
                  onChange={(value) => update("decisionPeriodStart", value)}
                />
                <DateField
                  id="decision-period-end"
                  label="Period end"
                  value={form.decisionPeriodEnd}
                  januaryOnly
                  onChange={(value) => update("decisionPeriodEnd", value)}
                />
              </div>
              <p className="field-hint">
                The decision window is separate from the delivery window.
              </p>
              <div className="form-grid two-columns cutoff-fields">
                <DateField
                  id="decision-date"
                  label="Decision date"
                  value={form.decisionDate}
                  januaryOnly
                  onChange={(value) => update("decisionDate", value)}
                />
                <TimeField
                  id="decision-cutoff"
                  label="Decision cutoff time (UTC)"
                  value={form.cutoffTime}
                  onChange={(value) => update("cutoffTime", value)}
                />
              </div>
              <p className="field-hint">
                One explicit decision date and cutoff are submitted. No daily
                cutoff rule is inferred for other dates in the period.
              </p>
            </fieldset>

            <fieldset>
              <legend>Delivery intervals</legend>
              <div className="form-grid two-columns">
                <DateTimeField
                  id="delivery-start-from"
                  label="Delivery start from (UTC)"
                  value={form.deliveryStartFrom}
                  onChange={(value) => update("deliveryStartFrom", value)}
                />
                <DateTimeField
                  id="delivery-start-to"
                  label="Delivery start to (UTC, exclusive)"
                  value={form.deliveryStartTo}
                  onChange={(value) => update("deliveryStartTo", value)}
                />
                <DateField
                  id="settlement-date-from"
                  label="Actual settlement date from"
                  value={form.settlementDateFrom}
                  onChange={(value) => update("settlementDateFrom", value)}
                />
                <DateField
                  id="settlement-date-to"
                  label="Actual settlement date to"
                  value={form.settlementDateTo}
                  onChange={(value) => update("settlementDateTo", value)}
                />
              </div>
            </fieldset>

            <fieldset>
              <legend>Forecast publication window</legend>
              <div className="form-grid two-columns">
                <DateTimeField
                  id="publish-from"
                  label="Published from (UTC)"
                  value={form.forecastPublishFrom}
                  onChange={(value) => update("forecastPublishFrom", value)}
                />
                <DateTimeField
                  id="publish-to"
                  label="Published to (UTC)"
                  value={form.forecastPublishTo}
                  onChange={(value) => update("forecastPublishTo", value)}
                />
              </div>
              <p className="field-hint">
                Include earlier publications when they could have been eligible
                at the decision cutoff.
              </p>
            </fieldset>

            <button className="analyze-button" type="submit" disabled={!canSubmit}>
              {loading ? (
                <>
                  <span className="spinner" aria-hidden="true" />
                  Analyzing…
                </>
              ) : (
                <>
                  Run analysis <span aria-hidden="true">→</span>
                </>
              )}
            </button>
          </form>
        </section>

        <section className="results-column" aria-labelledby="results-title">
          <div className="results-header">
            <div>
              <p className="eyebrow">ANALYSIS OUTPUT</p>
              <h2 id="results-title">Forecast review</h2>
            </div>
            <span className="step-number">02</span>
          </div>

          <div className="integrity-banner" role="status">
            <span className="integrity-icon" aria-hidden="true">!</span>
            <div>
              <strong>Accuracy metrics are blocked</strong>
              <p>
                WINDFOR units and interval semantics are unverified. Hourly
                forecasts must not be assumed comparable with half-hourly
                FUELHH actuals.
              </p>
            </div>
          </div>

          <div className="results-status" aria-live="polite" aria-busy={loading}>
            {loading ? (
              <div className="state-card loading-card">
                <span className="large-spinner" aria-hidden="true" />
                <h3>Retrieving Elexon records</h3>
                <p>Applying your decision cutoff to historical publications.</p>
              </div>
            ) : error ? (
              <div className="state-card error-card" role="alert">
                <span className="state-symbol" aria-hidden="true">!</span>
                <h3>Analysis could not be completed</h3>
                <p>{error}</p>
                <p className="field-hint">
                  Confirm the API is running at{" "}
                  <code>
                    {apiBaseUrl || "the local Vite proxy (http://localhost:8000)"}
                  </code>
                </p>
              </div>
            ) : analysis ? (
              <AnalysisResults analysis={analysis} />
            ) : (
              <div className="state-card empty-card">
                <div className="empty-illustration" aria-hidden="true">
                  <span />
                  <span />
                  <span />
                  <span />
                </div>
                <h3>Ready when you are</h3>
                <p>
                  Set an explicit decision cutoff and the separate delivery
                  and publication windows, then run the analysis.
                </p>
                <span className="empty-caption">
                  No forecast or actual records have been loaded yet.
                </span>
              </div>
            )}
          </div>
        </section>
      </div>

      <footer className="footer">
        <span>WINDSCOPE <span className="footer-dot">·</span> ANALYSIS FOUNDATION</span>
        <span>Data source: Elexon BMRS</span>
      </footer>
    </main>
  );
}

function DateField({
  id,
  label,
  value,
  januaryOnly = false,
  onChange,
}: {
  id: string;
  label: string;
  value: string;
  januaryOnly?: boolean;
  onChange: (value: string) => void;
}) {
  return (
    <label className="form-field" htmlFor={id}>
      <span>{label}</span>
      <input
        id={id}
        type="date"
        min={januaryOnly ? "2026-01-01" : undefined}
        max={januaryOnly ? "2026-01-31" : undefined}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        required
      />
    </label>
  );
}

function TimeField({
  id,
  label,
  value,
  onChange,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <label className="form-field" htmlFor={id}>
      <span>{label}</span>
      <input
        id={id}
        type="time"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        required
      />
    </label>
  );
}

function DateTimeField({
  id,
  label,
  value,
  onChange,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <label className="form-field" htmlFor={id}>
      <span>{label}</span>
      <input
        id={id}
        type="datetime-local"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        required
      />
    </label>
  );
}

function AnalysisResults({ analysis }: { analysis: AnalysisResponse }) {
  if (analysis.selected_forecasts.length === 0) {
    return (
      <div className="state-card empty-card compact-empty">
        <span className="state-symbol muted-symbol" aria-hidden="true">—</span>
        <h3>No selected forecasts in this scope</h3>
        <p>{analysis.metrics_block_reason}</p>
        <DataQuality analysis={analysis} />
      </div>
    );
  }

  return (
    <div className="analysis-results">
      <div className="block-detail">
        <span className="field-label">METRICS STATUS</span>
        <p>{analysis.metrics_block_reason}</p>
        <ul>
          {analysis.missing_verification_requirements.map((requirement) => (
            <li key={requirement}>{requirement}</li>
          ))}
        </ul>
      </div>

      <div className="result-scope">
        <span>Decision period</span>
        <strong>{analysis.decision_period_start} — {analysis.decision_period_end}</strong>
        <span>Delivery start window (UTC)</span>
        <strong>{analysis.delivery_start_from} — {analysis.delivery_start_to}</strong>
      </div>

      <DataQuality analysis={analysis} />

      <div className="forecast-list">
        <div className="list-heading">
          <div>
            <span className="field-label">WINDFOR RECORDS</span>
            <h3>Selected publications</h3>
          </div>
          <span className="record-count">
            {analysis.selected_forecasts.length} interval
            {analysis.selected_forecasts.length === 1 ? "" : "s"}
          </span>
        </div>
        {analysis.selected_forecasts.map((forecast, index) => (
          <ForecastCard key={`${forecast.decision_date}-${forecast.delivery_interval}-${index}`} forecast={forecast} />
        ))}
      </div>
    </div>
  );
}

function DataQuality({ analysis }: { analysis: AnalysisResponse }) {
  const quality = analysis.data_quality;
  return (
    <div className="quality-panel">
      <div className="quality-heading">
        <div>
          <span className="field-label">DATA CHECK</span>
          <h3>Data quality</h3>
        </div>
        <span className="quality-badge">RECORD COUNTS</span>
      </div>
      <div className="quality-grid">
        <QualityItem label="WINDFOR received" value={quality.forecast_records_received} />
        <QualityItem label="WINDFOR validated" value={quality.forecast_records_validated} />
        <QualityItem label="WINDFOR rejected" value={quality.forecast_records_rejected} />
        <QualityItem label="FUELHH received" value={quality.actual_records_received} />
        <QualityItem label="FUELHH validated" value={quality.actual_records_validated} />
        <QualityItem label="FUELHH rejected" value={quality.actual_records_rejected} />
        <QualityItem label="Non-wind excluded" value={quality.non_wind_records_excluded} />
        <QualityItem label="Ambiguous selections" value={quality.ambiguous_selection_count} />
      </div>
    </div>
  );
}

function QualityItem({ label, value }: { label: string; value: number }) {
  return (
    <div className="quality-item">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function ForecastCard({ forecast }: { forecast: SelectedForecast }) {
  const statusLabel = {
    selected: "Selected",
    no_eligible_forecast: "No eligible forecast",
    ambiguous: "Ambiguous",
  }[forecast.status];

  return (
    <article className="forecast-card">
      <div className="forecast-card-head">
        <div>
          <span className="field-label">DECISION DATE</span>
          <strong>{forecast.decision_date}</strong>
        </div>
        <span className={`selection-status status-${forecast.status}`}>
          {statusLabel}
        </span>
      </div>
      <dl className="forecast-details">
        <div>
          <dt>Delivery interval (UTC)</dt>
          <dd>{forecast.delivery_interval}</dd>
        </div>
        <div>
          <dt>Published (UTC)</dt>
          <dd>{timestampLabel(forecast.publish_time)}</dd>
        </div>
        <div>
          <dt>Original publication</dt>
          <dd>{timestampLabel(forecast.original_publish_time)}</dd>
        </div>
        <div>
          <dt>Decision cutoff (UTC)</dt>
          <dd>{forecast.decision_cutoff}</dd>
        </div>
        <div>
          <dt>Forecast generation (unit unverified)</dt>
          <dd>{forecast.generation === null ? "Not available" : forecast.generation}</dd>
        </div>
        <div>
          <dt>Eligible records considered</dt>
          <dd>{forecast.eligible_record_count}</dd>
        </div>
      </dl>
      {forecast.original_start_time && (
        <p className="original-time">
          Source startTime: <code>{forecast.original_start_time}</code>
        </p>
      )}
      <p className="rationale">{forecast.rationale}</p>
      {forecast.duplicate_information.length > 0 && (
        <p className="duplicate-note">
          Duplicate publications flagged: {forecast.duplicate_information.length}
        </p>
      )}
    </article>
  );
}

export default App;
