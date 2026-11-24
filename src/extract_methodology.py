"""Verify reviewed interpretation rules against the pinned CER methodology PDF.

The PDF is downloaded only with --fetch. Full text and official symbols are
not exported. Normal offline data builds use the committed reference JSON.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
URL = "https://apps2.cer-rec.gc.ca/pipeline-incidents/data/Incident%20Data%20Methodology_EN.pdf"
EXPECTED_SHA256 = "3b13337da8de1630a2d53361fe35c85d3a1b44d66050c43c11fbc34102e20678"
RULES = [
    {"id": "reported_date", "page": 4, "anchors": ["reported date/year", "occurred or was discovered"],
     "interpretation": "Reported year describes notification to the regulator, not necessarily occurrence or discovery."},
    {"id": "preliminary_status", "page": 2, "anchors": ["preliminary information", "subject to change"],
     "interpretation": "Initially Submitted and Submitted records can change as investigations progress."},
    {"id": "closed_review", "page": 2, "anchors": ["peer reviewer", "closed"],
     "interpretation": "Closed indicates completed regulatory review; it does not mean an incident never occurred."},
    {"id": "collection_change", "page": 3, "anchors": ["january 2015", "online event reporting system"],
     "interpretation": "The 2015 reporting-system change is relevant context for historical completeness comparisons."},
    {"id": "regulatory_company", "page": 4, "anchors": ["regulatory instrument"],
     "interpretation": "Company identifies the regulatory instrument holder; throughput-system names require a separate crosswalk."},
    {"id": "release_volume", "page": 6, "anchors": ["approximate volume released", "cubic metres"],
     "interpretation": "Released volume is approximate. Interpret substances separately and retain missing amounts."},
]


def normalized(text):
    return re.sub(r"\s+", " ", text).strip().casefold()


def dictionary_checks(path):
    raw = path.read_bytes()
    try:
        decoded = raw.decode("utf-8-sig")
        encoding = "utf-8-sig"
    except UnicodeDecodeError:
        decoded = raw.decode("cp1252")
        encoding = "cp1252"
    issues = []
    for row in csv.DictReader(io.StringIO(decoded, newline="")):
        field = row.get("Column", "").strip()
        description = normalized(row.get("Description of Data Value or Column Name", ""))
        if (field.casefold() == "latitude" and "longitude" in description
                or field.casefold() == "longitude" and "latitude" in description):
            issues.append({"field": field, "issue": "axis_description_mismatch",
                           "treatment": "Preserve the source; use named coordinate fields and range checks, without swapping axes."})
    return {"file": "data/source/incident_dictionary.csv", "encoding": encoding,
            "sha256": hashlib.sha256(raw).hexdigest(), "issues": issues}


def extract(path):
    try:
        import pypdf
        import fontTools
    except ImportError as error:
        raise SystemExit("Install requirements-source.txt to run the optional PDF extraction.") from error
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != EXPECTED_SHA256:
        raise ValueError("The methodology PDF differs from the reviewed snapshot; review it before updating rules.")
    reader = pypdf.PdfReader(io.BytesIO(raw))
    pages = [page.extract_text() or "" for page in reader.pages]
    if len(pages) != 7:
        raise ValueError("Unexpected methodology page count")
    verified = []
    for rule in RULES:
        text = normalized(pages[rule["page"] - 1])
        if not all(anchor in text for anchor in rule["anchors"]):
            raise ValueError(f"Expected interpretation evidence missing for {rule['id']}")
        verified.append({key: rule[key] for key in ("id", "page", "interpretation")} |
                        {"source_url": URL, "evidence_check": "passed"})
    metadata = reader.metadata or {}
    manifest = {
        "title": "Incident Data: Methodology - Incidents at CER-regulated Pipelines and Facilities",
        "publisher": "Canada Energy Regulator", "source_url": URL, "source_sha256": digest,
        "source_bytes": len(raw), "page_count": len(pages),
        "pdf_creation_date": str(metadata.get("/CreationDate", "")),
        "pdf_modified_date": str(metadata.get("/ModDate", "")),
        "extractor": "pypdf", "extractor_version": pypdf.__version__,
        "fonttools_version": fontTools.__version__,
        "pages": [{"page": index + 1, "text_characters": len(text),
                   "normalized_text_sha256": hashlib.sha256(normalized(text).encode()).hexdigest()}
                  for index, text in enumerate(pages)],
        "licence_scope": "CER website non-commercial reproduction terms; not the data's Open Government Licence.",
        "terms_url": "https://www.cer-rec.gc.ca/en/terms-conditions.html",
        "review_note": "Historical publisher methodology. PDF creation metadata is from 2019; these interpretation rules are not a statement of current law.",
        "dictionary_review": dictionary_checks(ROOT / "data/source/incident_dictionary.csv"),
    }
    return verified, manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch", action="store_true", help="Retrieve the pinned official PDF if not stored locally")
    args = parser.parse_args()
    path = ROOT / "data/source/incident_methodology.pdf"
    if args.fetch:
        raw = urllib.request.urlopen(URL, timeout=60).read()
        if hashlib.sha256(raw).hexdigest() != EXPECTED_SHA256:
            raise ValueError("Downloaded PDF differs from the reviewed snapshot; existing file left unchanged")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    if not path.exists():
        parser.error("PDF is not redistributed in Git; rerun with --fetch to retrieve the official source")
    rules, manifest = extract(path)
    out = ROOT / "data/reference"
    out.mkdir(parents=True, exist_ok=True)
    for name, content in [("methodology_rules.json", rules), ("methodology_extract_manifest.json", manifest)]:
        (out / name).write_text(json.dumps(content, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(f"Verified {len(rules)} reviewed interpretation rules against {manifest['page_count']} PDF pages; no full text exported")


if __name__ == "__main__":
    main()
