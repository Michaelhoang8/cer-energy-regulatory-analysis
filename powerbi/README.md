# Native Power BI report

Open [`native/CER_Energy_Analysis.pbip`](native/CER_Energy_Analysis.pbip) in Power BI Desktop and select **Refresh** to load the embedded data. The project includes a semantic model, Power Query import partitions, fifteen DAX measures and three editable report pages. CSV data are embedded in the model, so the project has no machine-specific source paths and requires no online account for these visuals.

| Page | Purpose |
|---|---|
| Point throughput | Compare mean daily throughput with reported capacity at one selected point; inspect paired-day utilization and observation coverage. |
| Incident reporting | Review counts by reported month and province, source review status, significance and usable coordinates. |
| Data quality | Inspect missing fields, negative observations, above-estimate throughput flags and expected/observed daily coverage. |

The initial selection follows the validated report metadata: currently calendar year 2025 and NGTL System's East Gate. Incident reporting uses its own province/year filters. Its data are not linked to individual throughput points.

## Model

`FactFlow` contains monthly aggregates of daily point observations. `FactIncident` retains one row per incident identifier. `DimMonth` filters both facts; `DimPoint` filters flow only; `DimProvince` filters incidents and point metadata through separate one-direction paths. There is no fact-to-fact relationship and no incident/throughput rate.

Rates and means are guarded by `HASONEVALUE(DimPoint[PointId])`. Selecting several points produces a blank rate because interconnected measurement points can report the same physical gas. Observation totals across points are explicitly called **point-days**, not total days or national throughput.

The [DAX measures](measures.dax) use these definitions:

- **Mean throughput:** valid daily volumetric-throughput sum divided by its valid-day count, at one point.
- **Mean capacity:** valid reported-capacity sum divided by its valid-day count, at one point.
- **Utilization:** sum of throughput divided by sum of capacity over the same paired valid days. Monthly percentages are never averaged.
- **Reporting coverage:** observed point-days divided by expected point-days, following the pipeline's documented active-series coverage policy.
- **Incident counts:** records grouped by reported month. Open means `Initially Submitted` or `Submitted`; significant means the source explicitly says `Yes`.

Volumetric rates are **thousand cubic metres per day**. The energy-throughput column in GJ/day is not mixed with volume. The observed monthly Brunswick series remains in the source archive and is excluded from the daily fact table.

The reported-capacity estimate can differ from capacity available in actual operating conditions. A value above the estimate is a review flag, not evidence of exceeding an operating limit. Incident counts do not have a comparable exposure denominator and are not a safety ranking. See the [CER's explanation](https://www.cer-rec.gc.ca/en/data-analysis/facilities-we-regulate/look-pipeline-flow-capacity/natural-pipeline-flow-capacity.html).

## Rebuild and validate

From the repository root, after running the data pipeline:

```bash
python src/build_powerbi.py
python -m unittest discover -s tests -v
```

For native-engine validation, open and refresh the project in Desktop. Use PowerShell **7 or later**, passing the local Analysis Services port for this report's Desktop workspace:

```powershell
pwsh -NoProfile -File src/validate_powerbi.ps1 -Port <local-port>
python src/compare_powerbi.py
```

The validator executes DAX for every point/year flow group, every province/year incident group and every measure in the model. The independent comparator recalculates all counts and weighted ratios from the SQL-built report payload. It also checks that global multi-point throughput, capacity and utilization measures remain blank. Results are written to `reports/powerbi_native_results.json` and `reports/powerbi_validation_results.json`.

This is an independent analysis using CER open data, not an official CER report. Contains information licensed under the Open Government Licence – Canada.
