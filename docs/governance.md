# Information management

| Layer | Contents | Access and lifecycle |
|---|---|---|
| Source | Original official CSVs, GeoJSON and metadata | Publicly published inputs; immutable within the pinned snapshot. SHA-256 checks fail if bytes change. |
| Reference | Paraphrased PDF rules and extraction provenance | Public derived documentation; full historical PDF is excluded from Git under its separate reproduction terms. |
| Audit database | Raw daily measurements, source identifiers, duplicate-key review and normalized incidents | Rebuilt locally from the snapshot; excluded from Git. Retains the original measurement signs and nulls. |
| Model | Dimension tables and monthly/day-count aggregates | Public CSVs with documented grain and units; generated, never manually corrected. |
| Report | Findings, offline dashboard, Power BI, Excel, screenshots and walkthrough | Public outputs; evidence hashes and validation results identify the report being reviewed. |

The project uses public government data only. It contains no user credentials, private CER systems or internal operational records. Review-owner/status fields in the Excel workbook are a local demonstration, not assignments to real staff or evidence of tenant integration.

## Refresh and correction procedure

1. Download official sources into a separate candidate snapshot; record URL, publisher, time, bytes, encoding and checksum.
2. Profile schema, grain, dates, frequency and units before accepting the candidate. Retain monthly sources separately from daily measures.
3. Rebuild and inspect reconciliation and quality differences. Record substantive interpretation decisions in the methodology.
4. Refresh Power BI and Excel outputs. Re-run native DAX comparisons and capture evidence; stale screenshot/report hashes fail verification.
5. Commit the source and results together using the actual update date. Existing source values are never silently patched to make checks pass.

`scripts/fetch_sources.py` writes a candidate snapshot outside the active source directory by default. It does not promote a new extract automatically. This prevents a partial download or changed upstream schema from replacing the reviewed snapshot.

## Retention and retrieval

This portfolio retains its published source snapshot and provenance for reproducibility. The SQLite cache and temporary render files are disposable. This is a project retention decision, not an assertion about CER retention schedules or government records-disposition authority. Source records are retrieved by file and 1-based CSV-record number, or by Incident Number. CSV-record numbers are not physical line numbers because fields can contain line breaks.

Data stewardship questions include ambiguous units, reporting frequency, interpretation of missing values and generalized spatial boundaries. Findings remain review items until confirmed by an authoritative source; neither an automated flag nor a nonzero exception count establishes noncompliance.
