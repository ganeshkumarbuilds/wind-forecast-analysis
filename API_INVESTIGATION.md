# Elexon BMRS API Investigation

**Purpose:** Document the Elexon API findings for WindScope's analysis of UK wind-generation forecasts relevant to purchasing decisions made in January 2026, compared with actual generation.

**Evidence basis:** Official Elexon endpoint documentation and OpenAPI specification, plus direct requests to the official API on 23 October 2026. This document distinguishes documented facts from results observed in those requests and from unresolved business or data questions. No application code or API assumptions beyond those findings are included.

## 1. Official endpoints

The documentation URLs are interactive documentation pages, not the data endpoints. The official OpenAPI specification identifies the API server as `https://data.elexon.co.uk/bmrs/api/v1`.

- FUELHH stream: `GET https://data.elexon.co.uk/bmrs/api/v1/datasets/FUELHH/stream`
- WINDFOR stream: `GET https://data.elexon.co.uk/bmrs/api/v1/datasets/WINDFOR/stream`

Official references:

- [FUELHH stream documentation](https://bmrs.elexon.co.uk/api-documentation/endpoint/datasets/FUELHH/stream)
- [WINDFOR stream documentation](https://bmrs.elexon.co.uk/api-documentation/endpoint/datasets/WINDFOR/stream)
- [Official OpenAPI specification](https://data.elexon.co.uk/swagger/v1/swagger.json)

The endpoint name `/stream` does not mean the response is newline-delimited or incrementally paginated: the verified response was a JSON array.

## 2. Supported parameters, response format, and authentication

### FUELHH

The OpenAPI specification documents these query parameters:

- `publishDateTimeFrom`, `publishDateTimeTo`: publication-time bounds, date-time values.
- `settlementDateFrom`, `settlementDateTo`: settlement-date bounds in `yyyy-MM-dd` form.
- `settlementPeriod`: one or more settlement periods.
- `fuelType`: one or more fuel types, including `WIND`.

The FUELHH documentation says settlement-date parameters cannot be combined with publication-date parameters. For delivery-date actuals, query by settlement date and filter to `fuelType=WIND`.

### WINDFOR

The OpenAPI specification documents:

- `publishDateTimeFrom`, `publishDateTimeTo`: publication-time bounds, date-time values.

No delivery-`startTime` filter is documented for this endpoint. To choose forecasts for delivery intervals, retrieve publication windows and filter or group by `startTime` in the analysis.

### Responses and access

Both stream endpoints returned HTTP 200 with `Content-Type: application/json; charset=utf-8` and a JSON array of records. The API specification also lists HTTP 400, 429, and 500 responses.

The specification contains no pagination or cursor parameters and no authentication scheme for these endpoints. Requests used in this investigation succeeded without credentials. The specification does not state a numeric rate limit.

Use the documented parameter names. In particular, a probe using `from` and `to` returned current/latest records rather than the requested historical period; those are not the documented historical filter names.

## 3. Verified historical availability for January 2026

Direct API requests made on 23 October 2026 verified that January 2026 records were retrievable:

- FUELHH, queried using `settlementDateFrom=2026-01-01`, `settlementDateTo=2026-01-31`, and `fuelType=WIND`, returned **1,488 records**. They covered **1,488 distinct half-hour `startTime` values**, from `2026-01-01T00:00:00Z` through `2026-01-31T23:30:00Z`.
- WINDFOR, queried using `publishDateTimeFrom=2026-01-01T00:00:00Z` and `publishDateTimeTo=2026-02-01T00:00:00Z`, returned **18,104 records** and **248 distinct January `publishTime` values**. The returned records retained publication timestamps in January 2026; they were not relabeled with the retrieval time.
- The January-publication WINDFOR response included delivery `startTime` values through `2026-02-02T21:00:00Z`. January decisions can therefore relate to February delivery.

These are observed results for the tested queries and retrieval date, not a guarantee of future API availability or complete coverage for every possible decision cutoff.

## 4. Fields, timestamps, and units

The inspected response schemas and examples show:

- **FUELHH:** `fuelType`, `startTime`, and `publishTime` are strings; `generation` is an integer. Records also include `dataset`, `settlementDate`, and `settlementPeriod`.
- **WINDFOR:** `startTime` and `publishTime` are date-time strings; `generation` is an integer. Records also include `dataset`.
- The schema marks some fields, including `generation`, as nullable. Consumers should validate values rather than assume every record is complete.
- Returned timestamps observed in both datasets use ISO 8601 UTC notation ending in `Z`. Use UTC instants for comparisons and joins; convert to `Europe/London` for local business-date display. January 2026 is GMT, but UTC and local dates can differ around midnight in other periods.

The FUELHH endpoint description explicitly states that its half-hourly generation is an average in **MW over 30 minutes**.

WINDFOR records sampled in the investigation had hourly `startTime` intervals. However, the inspected WINDFOR endpoint schema and description do **not** establish the generation unit or sufficiently specify the interval's averaging semantics. These remain unverified. Do not label WINDFOR generation as MW or assume it is directly comparable with half-hourly FUELHH without an authoritative definition and a decision on evaluation grain.

## 5. Actual and forecast interval differences

FUELHH actuals are half-hourly. WINDFOR rows observed in the API responses were hourly. An equality join on `startTime` alone will therefore not pair every half-hour actual with a forecast.

Before calculating errors, establish the forecast interval semantics and select a common comparison grain. Do not duplicate or interpolate hourly forecast values across half-hours unless that method is explicitly approved and documented.

## 6. Forecast selection without look-ahead bias

For each purchasing decision and delivery interval:

1. Identify the delivery interval using `startTime`, normalized to UTC.
2. Determine the applicable decision timestamp and business-approved purchasing cutoff.
3. Exclude any forecast with `publishTime` after that cutoff.
4. Select the eligible forecast with the latest `publishTime` for each delivery interval.
5. Match the selected forecast to FUELHH actual generation for the same delivery interval after resolving the hourly-versus-half-hourly comparison grain.
6. Surface missing intervals, null values, and conflicting duplicates in validation results; do not silently drop them or select an arbitrary record.

Preserve publication history until eligibility and latest-forecast selection have been applied. Collapsing forecasts to a single row per `startTime` beforehand can erase the historical publication needed to reconstruct what was known at decision time.

The January WINDFOR query returned 18,104 rows, with 793 distinct delivery start times and no duplicate `(publishTime, startTime)` pairs in that response. This is an observation from the tested result, not a guarantee for all periods or future data.

## 7. Decision dates versus delivery dates

Keep the purchasing decision date separate from the delivery date. A decision made on **31 January** for a delivery interval in **February** belongs to a January decision cohort but not to a January delivery-performance cohort.

When evaluating decisions made in January, include forecast deliveries beyond January when those decisions concern them, and retrieve the corresponding actuals. For delivery-period reporting, classify intervals by their delivery date independently of the date the decision was made.

## 8. Retrieval, caching, validation, and error handling

- Retrieve FUELHH actuals by settlement-date range and filter `fuelType=WIND`. Include the full delivery-date range being evaluated, including February actuals if January decisions concern February delivery.
- Retrieve WINDFOR by publication-time windows. Include December publications for early-January decisions; limiting publication queries to January can omit forecasts eligible at the beginning of the month.
- The tested January WINDFOR request returned about 2.0 MB (18,104 rows). A wider request from 28 December through 1 February returned 20,440 rows (about 2.3 MB). Since there is no documented pagination, use manageable publication-time chunks for larger ranges, overlap boundaries where appropriate, and deduplicate overlapping results using stable record keys.
- Persist raw responses and retrieval timestamps so forecast history can be audited and analysis does not depend on an API request at dashboard viewing time.
- Validate HTTP status, response shape, required fields, timestamps, and nulls. Check expected half-hourly actual coverage and forecast publication/delivery coverage, and report gaps instead of silently treating them as zero.
- Detect duplicates and conflicting values explicitly. Deduplicate overlapping fetches only with a defined key and preserve or flag conflicting records.
- Handle HTTP 429 and 5xx errors explicitly with bounded retries and backoff. Do not replace a failed historical request with latest/current data or return a success-shaped empty result.
- Track data freshness and show a clear stale-data or retrieval-error state if refresh fails. No numeric API quota or rate limit was established by the official specification or this investigation.

## 9. Limitations and unresolved questions

1. **Purchasing cutoff is unresolved.** Neither the inspected API documentation nor OpenAPI specification establishes the business purchasing decision cutoff. The business must define the decision timestamp, timezone, and whether the cutoff varies by delivery interval. Do not invent or present a cutoff time as a verified rule.
2. **WINDFOR generation unit and interval semantics are unverified.** The response schema specifies an integer but does not confirm units or sufficiently define the hourly forecast value.
3. **Comparison grain is unresolved.** Hourly WINDFOR records and half-hourly FUELHH actuals require an approved alignment method before forecast errors can be calculated.
4. **No pagination mechanism or numeric rate limit was found in the inspected specification.** Large responses, service limits, and operational behavior should be monitored; HTTP 429 is documented.
5. **Historical observations are bounded by the tested requests.** Successful retrieval of January 2026 data on 23 October 2026 does not guarantee indefinite retention, availability, or complete coverage for every cutoff and delivery horizon.
6. **WINDFOR has no documented `startTime` query filter.** Retrieval completeness for decision analysis depends on publication-window coverage followed by local delivery-interval filtering and explicit checks for missing eligible forecasts.
7. **Early-January decision coverage needs December publications.** The exact lookback needed depends on the business cutoff and delivery scope. The observed maximum lead in the wider sample was 66.5 hours; that is only an observation, not a documented maximum forecast horizon.
8. **Decision and delivery cohorts must remain separate.** January decisions may target February deliveries, so the reporting scope and actual-data retrieval window must be defined accordingly.

## 10. Focused comparability investigation (23 October 2026)

This follow-up used the official OpenAPI document and bounded requests to the official stream endpoints. It does not change the analysis service's blocked-metrics behavior.

### 10.1 WINDFOR unit and interval semantics

**Verified from official documentation:** The WINDFOR operation description in the [official OpenAPI specification](https://data.elexon.co.uk/swagger/v1/swagger.json) says only: “This endpoint provides wind generation forecast data.” Its response schema defines `generation` as a nullable `integer` with `int64` format and defines `startTime` and `publishTime` as date-time strings. It gives no unit for `generation`, and no description saying whether the quantity is instantaneous power, an hourly average, energy over an hour, or something else. The [WINDFOR endpoint documentation](https://bmrs.elexon.co.uk/api-documentation/endpoint/datasets/WINDFOR/stream) is a JavaScript-rendered page; the OpenAPI specification is the inspectable schema source used here.

**Observed, not a semantic definition:** In the bounded January sample below, forecast `startTime` values for each publication are one hour apart. This supports saying that the sample has hourly timestamp spacing; it does not establish that each value represents an hourly mean or energy over that hour. The magnitudes (for example, `11800`) are not evidence of units.

**Finding:** No authoritative WINDFOR unit or measurement-interval definition was found in the inspected Elexon endpoint documentation or OpenAPI schema. These remain unresolved; do not label the values MW or MWh or describe them as hourly averages.

### 10.2 FUELHH actual semantics and timestamp evidence

**Verified from official documentation:** The FUELHH operation description in the [official OpenAPI specification](https://data.elexon.co.uk/swagger/v1/swagger.json) states: “This endpoint provides the half-hourly generation outturn (Generation By Fuel type)” and “The data is aggregated by Fuel Type category and updated at 30-minute intervals with average MW values over 30 minutes for each category.” Thus, `generation` is average power in MW over a 30-minute interval, not a 30-minute energy quantity in MWh. The [FUELHH endpoint documentation](https://bmrs.elexon.co.uk/api-documentation/endpoint/datasets/FUELHH/stream) is the corresponding official endpoint reference.

The OpenAPI response schema types FUELHH `startTime` as a nullable date-time string and `settlementPeriod` as a nullable integer, but provides no property-level description explicitly defining which boundary `startTime` labels. In the sampled response, settlement period 1 has `startTime=2026-01-05T00:00:00Z` and period 48 has `startTime=2026-01-05T23:30:00Z`. This is consistent with `startTime` being the beginning of each 30-minute interval. The documentation establishes the 30-minute interval and average-MW quantity; the explicit boundary wording is not present in the inspected schema.

For the sampled historical date, the API returned all 48 settlement periods, with distinct `startTime` values every 30 minutes from 00:00 through 23:30 UTC. This observed count and spacing are consistent with 48 half-hour settlement periods for that day; they do not replace the endpoint's explicit measurement description.

### 10.3 Bounded January 2026 API sample

Requests made to the official API on 23 October 2026:

```text
GET https://data.elexon.co.uk/bmrs/api/v1/datasets/FUELHH/stream?settlementDateFrom=2026-01-05&settlementDateTo=2026-01-05&fuelType=WIND
GET https://data.elexon.co.uk/bmrs/api/v1/datasets/WINDFOR/stream?publishDateTimeFrom=2026-01-05T00:00:00Z&publishDateTimeTo=2026-01-06T00:00:00Z
```

These were one settlement date and one publication day, not the full historical datasets. Sensitive information is not present in these public dataset rows.

**FUELHH result:** 48 records, 48 distinct `startTime` values; first 00:00Z, last 23:30Z; every adjacent start was 30 minutes apart. No duplicate `startTime` values were observed. Example first, middle, and final records:

```json
{"dataset":"FUELHH","publishTime":"2026-01-05T00:30:00Z","startTime":"2026-01-05T00:00:00Z","settlementDate":"2026-01-05","settlementPeriod":1,"fuelType":"WIND","generation":10601}
{"dataset":"FUELHH","publishTime":"2026-01-05T12:00:00Z","startTime":"2026-01-05T11:30:00Z","settlementDate":"2026-01-05","settlementPeriod":24,"fuelType":"WIND","generation":10305}
{"dataset":"FUELHH","publishTime":"2026-01-06T00:00:00Z","startTime":"2026-01-05T23:30:00Z","settlementDate":"2026-01-05","settlementPeriod":48,"fuelType":"WIND","generation":6100}
```

**WINDFOR result:** 584 records from 8 distinct `publishTime` values. Those observed publication times were `02:30Z`, `04:30Z`, `07:30Z`, `09:30Z`, `11:30Z`, `15:30Z`, `18:30Z`, and `22:30Z` on 5 January. The publication cadence in this one-day sample is irregular; it is not evidence of a guaranteed schedule. Each publication had 73 distinct delivery `startTime` values, hourly spaced from `2026-01-04T21:00:00Z` through `2026-01-07T21:00:00Z`. There were no repeated `(publishTime, startTime)` pairs in the sample. There were no gaps within those observed consecutive hourly labels for each publication. This does not establish expected coverage outside the sampled runs or the meaning of the forecast quantity.

Example first, middle, and final rows from the 22:30Z publication:

```json
{"dataset":"WINDFOR","publishTime":"2026-01-05T22:30:00Z","startTime":"2026-01-04T21:00:00Z","generation":11800}
{"dataset":"WINDFOR","publishTime":"2026-01-05T22:30:00Z","startTime":"2026-01-05T12:00:00Z","generation":9322}
{"dataset":"WINDFOR","publishTime":"2026-01-05T22:30:00Z","startTime":"2026-01-07T21:00:00Z","generation":7831}
```

All timestamps in these sampled rows are ISO-8601 strings ending in `Z`, denoting UTC. The sample is an observation of this response, while the response schema itself promises date-time strings, not that every historical record must use the same textual offset notation. No duplicate/conflicting records were observed for the tested keys; this does not establish that duplicates never occur.

### 10.4 Comparison feasibility and conditional methods

**Current evidence does not support direct comparison.** FUELHH is officially average MW over half-hour intervals. For WINDFOR, neither the unit nor the meaning and duration associated with a `startTime` are authoritatively established. Matching values at the same timestamp, or noting that forecast timestamps are hourly, cannot resolve that gap.

No temporal transformation is defensible until the WINDFOR definition is obtained. If an authoritative source later establishes that a WINDFOR value is **average MW over the hour beginning at `startTime`**, a possible hourly comparison would be the duration-weighted mean of the two corresponding FUELHH half-hour average-MW records:

```text
actual_hourly_mean_MW = (actual_halfhour_1_MW * 0.5h
                         + actual_halfhour_2_MW * 0.5h) / 1h
```

That operation assumes contiguous, complete half-hour actual intervals covering exactly the same hour, matching interval boundaries, consistent MW definitions, and an approved comparison grain. If WINDFOR is instead hourly energy, the compatible actual would be the two half-hour average-MW values multiplied by 0.5 hours and summed to MWh. If it is an instantaneous forecast, an interval average is not equivalent; a point-in-time comparison rule would need to be specified. These are conditional examples, not assertions about WINDFOR or an implemented method.

Until the WINDFOR unit, value semantics, and timestamp interval boundary are authoritatively defined—and a comparison grain is approved—the defensible conclusion is **no real-data accuracy comparison**. Keep metrics blocked; do not resample, duplicate, interpolate, or aggregate actuals in the application yet.

### 10.5 Purchasing decision cutoff

The inspected Elexon FUELHH and WINDFOR operation descriptions and OpenAPI parameters expose data/publication filters but do not specify a purchasing decision cutoff. The assignment also does not identify a particular day-ahead market, exchange, product, buyer process, timezone, or transaction type whose gate-closure rule could be applied. Therefore, no universal or assignment-specific cutoff was verified. Obtain an explicit business rule (including timezone and whether it varies by delivery) before interpreting a cutoff. The API's `publishTime` filter is not itself a purchasing cutoff.
