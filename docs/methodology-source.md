# Methodology document evidence

The unstructured reference is the Canada Energy Regulator's [Incident Data: Methodology - Incidents at CER-regulated Pipelines and Facilities](https://apps2.cer-rec.gc.ca/pipeline-incidents/data/Incident%20Data%20Methodology_EN.pdf). The extraction reads all seven pages and verifies six reviewed interpretations against expected phrases. Page-level hashes and source metadata make the result traceable without republishing the document.

The PDF's creation metadata is dated October 2019. It provides historical data context; the project does not use it to determine current legal compliance. See [reviewed rules](../data/reference/methodology_rules.json) and [extraction manifest](../data/reference/methodology_extract_manifest.json).

The [CER website terms](https://www.cer-rec.gc.ca/en/terms-conditions.html) govern the document separately from the open-data licence. The original PDF, its official symbols and full extracted text are not redistributed. This independent interpretation was not produced in affiliation with or endorsed by the CER.

Optional reproduction of the extraction:

```bash
python -m pip install -r requirements-source.txt
python src/extract_methodology.py --fetch
```

Normal offline builds use the committed reference JSON. A changed upstream PDF causes extraction to fail pending review instead of silently replacing the reviewed interpretations.

The source CSV dictionary also contains reversed axis descriptions for its Latitude and Longitude entries. The original dictionary is retained unchanged. The pipeline uses the named coordinate columns, validates numeric ranges and applies a separate spatial review; it does not swap axes based on those descriptions.
