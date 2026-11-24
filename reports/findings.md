# Regulatory data review

## Scope

The daily model contains 279,055 published observations at 44 distinct pipeline/key-point/direction/trade combinations across seven natural-gas systems. Source coverage is 2006-01-01 through 2026-09-30. Brunswick's 206 monthly observations are retained as a source but excluded from daily coverage calculations.

The comprehensive incident extract contains 2,039 distinct incident IDs. It spans multiple energy products and regulated facilities; it is a separate reporting population. The incident extract's latest reported date is 2026-10-22.

## Selected-point result

NGTL System, East Gate, 2025 has 365 observed daily records and 365 paired observations. Capacity-weighted utilization is 104.13%. There are 247 observations above reported capacity. CER explains that reported capacity is estimated and can be exceeded; this is not a finding of noncompliance.

## Incident reporting

There are 68 incidents reported in 2025. Status and significance reflect the extract date, not what was known at the end of 2025. Counts describe reported incidents, not exposure-adjusted safety performance.

## Source reconciliation

The comprehensive extract and the separate public incident-map feed are reconciled by Incident Number. Counts: {"matched": 2039}. See `incident_reconciliation.csv` for every ID and differing fields. Neither publication overwrites the other; coverage, timing and schema differences require source-owner review.

## Recommended review actions

1. Review missing capacity/throughput as distinct completeness issues. Keep null values out of paired ratios; do not convert them into zero flow or zero capacity.
2. Preserve signed flows and capacity exceedances for source confirmation. Avoid clipping values to make a chart appear compliant.
3. Resolve documented dictionary inconsistencies with the publisher: volumetric capacity versus energy units, and reversed coordinate descriptions. Keep the original metadata and the explicitly documented interpretation.
4. Review source-ID differences and GIS province differences using the original record references. Generalized boundaries and approximate incident coordinates do not establish a location error.
5. Keep the completed 2025 comparison cohort separate from partial 2026 data. Review per-source dates and first/last observations before interpreting change.

## Limits

The project does not infer pipeline outages, operational availability, regulatory breaches, actual damages, causal relationships or a company safety ranking. Multiple key points can observe the same gas. No network flow total or incidents-per-volume metric is calculated. Calendar coverage is bounded by each series' first and last published observation and cannot identify missing observations beyond those boundaries.

Contains information licensed under the Open Government Licence – Canada.
