# Analytical methods

## Questions and grain

The flow report asks how published throughput and estimated capacity change at a selected measurement point, and whether the observations are complete enough for that comparison. The incident report asks where and when incidents were reported and how source records reconcile. These are separate populations: seven natural-gas systems versus incidents across CER-regulated products and facilities. No incident-per-volume metric is calculated.

A daily flow key is **date × pipeline × key point × direction × trade type**. A stable PointId hashes the four non-date fields; company names are attributes, not proof of a historical corporate identity. Exact raw-field repetitions are removed. All conflicting, nonidentical rows sharing a daily key are excluded from analytical aggregates and remain in `flow_raw` and `conflicting_keys` for review. The current source snapshot has neither kind of duplication.

`FactFlow` has monthly point-level observations. `FactIncident` has one row per Incident Number. `DimPoint`, `DimMonth` and `DimProvince` provide explicit dimensions. `SourceFile`, `SourceRow` and `RowHash` preserve daily lineage in the local SQLite database; incident source rows are retained in the JSON report and audit table.

## Frequency and units

Seven input systems report daily: NGTL, Canadian Mainline, Foothills, Alliance, Westcoast, Trans Québec & Maritimes, and Maritimes & Northeast. The Brunswick extract has monthly observations and is retained as a separate source, excluded from daily coverage. The decision comes from profiling actual date intervals rather than assuming every file in a catalogue has the same frequency.

Rate columns explicitly identify **1000 m³/day**. The gas dictionary's capacity description instead says GJ/day; this inconsistency is recorded. The analysis uses the column header units. GJ/day is retained in its own audit column and never added to or substituted for volumetric flow. Original metadata remains unchanged.

At one point, utilization is `sum(paired throughput rates) / sum(paired capacity rates)`. Both numbers must be finite and capacity strictly positive on the same day. Nulls do not become zero. Mean throughput and mean capacity use their respective valid-observation counts, which can differ from the paired count. Zero capacity is a reported value but cannot enter the utilization denominator. Negative throughput retains its sign and receives a review flag.

CER states that reported capacity is estimated and throughput can exceed it. A ratio above 100% is retained; it does not establish a breach. Multiple measurement points can observe the same gas, so rates are never presented as an arbitrary network total. Native DAX rate measures return blank unless exactly one PointId is selected. [CER's flow and capacity explanation](https://www.cer-rec.gc.ca/en/data-analysis/facilities-we-regulate/look-pipeline-flow-capacity/natural-pipeline-flow-capacity.html).

## Coverage and dates

Expected dates run from the first to the last published observation for each point, inclusive. This detects internal calendar gaps, not missing history outside those bounds, outages, operating availability or required reporting obligations. Rows with missing numeric measures still count as observed dates; numeric completeness is reported separately. Empty months inside a series window receive zero observed dates and their actual calendar denominator, including leap days.

The default comparison year is the last calendar year preceding the latest flow observation year: 2025 for this snapshot. Partial 2026 observations remain available. Source endpoints are shown independently; incidents and flow need not have the same publication schedule.

Incident cohorts use **Reported Date**, not an inferred occurrence date. The comprehensive input uses month/day/year; the map extract adds a time component. Both formats are parsed explicitly and compared as calendar dates. Status reflects the source snapshot, not the status at the reporting-year end. Closed-to-reported day intervals are optional descriptive fields, with negative/invalid intervals excluded; they are not service-level or investigation-efficiency measures.

## Reconciliation

Two official incident publications are joined on Incident Number. IDs must be populated and unique in each source. The comparison covers organization, normalized province, status, significance, reported date, and coordinates when those columns exist. Coordinates use an absolute tolerance of 0.00001 degrees. The complete result is exported to `reports/incident_reconciliation.csv`; unmatched IDs or field differences never silently replace the other publication.

Known province names/codes are normalized consistently. Unknown labels, including the published US state Maine, are retained in both sources. This prevents a Canadian lookup table from manufacturing a false mismatch. All 2,039 IDs and compared fields reconcile in this snapshot. Other fields may differ or be absent and are not implied to have been compared.

## Spatial assessment

The incident dictionary reverses its latitude and longitude descriptions. The CSV headers and valid coordinate ranges determine axis order; the data are not automatically swapped. Latitude/longitude values are interpreted in the published order and checked against NRCan's generalized EPSG:4326 province polygons. The spatial implementation handles Polygon/MultiPolygon parts, holes, boundary points and non-finite coordinates.

The 114 polygon parts represent 13 provinces/territories. A spatial result is one of `match`, `mismatch_review`, `outside_generalized_boundary`, `invalid_coordinates`, `unknown_reported_province`, or `boundary_review`. The current snapshot has 1,996 matches and 43 other review statuses. A review status does not prove the source location is wrong: boundary simplification, approximate points, border cases and locations outside the Canadian province dictionary matter. Original and spatially inferred provinces are both retained.

No licensed pipeline-route geometry is redistributed. The map displays openly licensed province boundaries and published observation/incident points for context, not legal boundaries, engineering measurements or route reconstruction.

## Unstructured methodology source

The optional PDF workflow extracts and verifies page-level evidence from a historical CER methodology document. Six short paraphrased rules and provenance are saved under `data/reference`. It is supporting documentation, not a claim about current legal requirements. See [the source-specific licence and extraction notes](methodology-source.md).
