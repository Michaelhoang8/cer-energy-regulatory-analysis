# Project evidence for regulatory data analysis

This project is aligned with the technical work described in the Canada Energy Regulator Regulatory Data Analyst posting supplied for reference. It is independent portfolio work. It does not establish employment history, qualifications, access to internal CER systems, or experience with products that were not used.

| Requirement | Concrete project evidence |
|---|---|
| E1 — collect, clean, validate, prepare and maintain multi-source data | Seven daily gas files, a separately profiled monthly feed, two incident publications, province geometry and historical methodology; source hashes, encoding handling, grain checks, null policies and traceable review outputs. |
| E2 — dashboards and reporting | Editable native Power BI report, DAX measures, an Excel review workbook with formulas and editable review status, plus an offline report with filters and a map. Screenshots and a continuous browser walkthrough demonstrate actual outputs. |
| E3 — explore, analyze and reconcile relational, unstructured and semi-structured data | SQLite audit tables and SQL monthly views; incident-ID reconciliation across two CSV publications; GeoJSON point-in-polygon checks; optional PDF text extraction with page-level provenance and verified rule anchors. |
| AQ1 — SQL | Explicit relational schema, grouped reporting views, source-key conflict handling and independently checked totals. |
| AQ2 — GIS | Official NRCan Polygon/MultiPolygon boundaries, EPSG:4326 axis handling, holes/boundary cases, published point coordinates and spatial review statuses. |
| AQ3 — information management | Documented source catalogue, lineage, snapshot lifecycle, access scope, local retention decision and retrieval by source record. |
| AQ6 — Canadian energy knowledge | Estimated capacity versus throughput, physical double counting across key points, volume/energy unit separation, incident-reporting scope and publication timing. |
| TC1 — requirements analysis | Business questions mapped to point-level operational reporting, source reconciliation and review queues; grain and denominator choices are stated before interpretation. |

SharePoint, Microsoft 365 tenant administration and Copilot are **not** implemented or claimed. The project also does not substitute for the posting's education, employment or other screening requirements.

## Reproducible examples to discuss

- A gas source dictionary uses an energy unit in the description of a volumetric capacity column. The original metadata is retained, the explicit header unit is used consistently, and the issue is documented.
- Missing capacity is excluded from paired utilization calculations without converting missing throughput into zero. Mean throughput and mean capacity retain separate denominators.
- A monthly gas feed is excluded from daily coverage. Calendar coverage measures internal record completeness, not pipeline availability.
- Canadian province normalization initially needs an explicit fallback for a published Maine record. Preserving the unknown label consistently avoids manufacturing a discrepancy between two matching sources.
- Spatial differences are reported with their original coordinates and province labels. Generalized geometry is treated as a review aid rather than proof of source error.

Use these as project examples only after reviewing the code, results and limitations. They do not describe stakeholder interviews, deployed workflows or manual development sessions that did not occur.
