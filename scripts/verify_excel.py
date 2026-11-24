"""Read-only XLSX inspection and UTF-8-safe validation metadata updates."""

import hashlib
import json
from pathlib import Path
from zipfile import ZipFile
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
NS = {
    "s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "c": "http://schemas.openxmlformats.org/drawingml/2006/chart",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
}


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def text_values(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, child in value.items():
            yield key
            yield from text_values(child)
    elif isinstance(value, list):
        for child in value:
            yield from text_values(child)


def main():
    metadata_path = ROOT / "reports/excel_validation.json"
    report = json.loads(metadata_path.read_text(encoding="utf-8"))
    payload_path = ROOT / report["input_file"]
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    point = next(row for row in payload["points"] if row["PointId"] == report["point_id"])
    assert report["input_sha256"] == sha256(payload_path), "Workbook input snapshot has changed"
    assert report["point_label"] == point["PointLabel"], "Point label differs from UTF-8 payload"

    workbook_path = ROOT / report["workbook"]
    with ZipFile(workbook_path) as archive:
        files = archive.namelist()
        xml_strings = []
        for filename in files:
            if filename.endswith(".xml"):
                document = ET.fromstring(archive.read(filename).decode("utf-8"))
                xml_strings.extend(document.itertext())
        sheets = [n for n in files if n.startswith("xl/worksheets/sheet") and n.endswith(".xml")]
        charts = [n for n in files if "/charts/chart" in n and n.endswith(".xml")]
        exported = {
            "sheet_count": len(sheets),
            "chart_count": len(charts),
            "formula_count": 0,
            "error_cells": [],
            "validations": [],
            "chart_series": [],
            "native_tables": len([n for n in files if n.startswith("xl/tables/table") and n.endswith(".xml")]),
        }
        for filename in sheets:
            document = ET.fromstring(archive.read(filename))
            exported["formula_count"] += len(document.findall(".//s:f", NS))
            exported["error_cells"].extend(
                [filename, cell.attrib["r"]]
                for cell in document.findall(".//s:c", NS)
                if cell.attrib.get("t") == "e"
            )
            exported["validations"].extend(rule.attrib for rule in document.findall(".//s:dataValidation", NS))
        for filename in charts:
            document = ET.fromstring(archive.read(filename))
            for series in document.findall(".//c:ser", NS):
                exported["chart_series"].append({
                    "chart": filename,
                    "formulas": [el.text for el in series.findall(".//c:f", NS)],
                    "stroke_colors": [el.attrib for el in series.findall(".//a:ln/a:solidFill/a:srgbClr", NS)],
                    "stroke_styles": [el.attrib for el in series.findall(".//a:ln/a:prstDash", NS)],
                })

    assert exported["sheet_count"] == 3
    assert exported["chart_count"] == 2
    assert exported["native_tables"] == 3
    assert exported["formula_count"] > 100
    assert len(exported["validations"]) == 1
    assert not exported["error_cells"]
    suspicious = ("\ufffd", "\u00c2\u00b7", "\u00c2\u00b3", "\u00c3\u00a9", "\u00e2\u20ac")
    assert not any(marker in value for value in text_values(report) for marker in suspicious), "Suspicious encoding in validation text"
    assert not any(marker in value for value in xml_strings for marker in suspicious), "Suspicious encoding in XLSX text"
    workbook_text = "\n".join(xml_strings)
    for url in payload["meta"]["source_urls"].values():
        assert url in workbook_text, f"Missing source URL in XLSX: {url}"
    report["export_verification"] = exported
    report["text_encoding_checks"] = {
        "metadata_utf8_roundtrip": True,
        "xlsx_xml_utf8_decoding": True,
        "source_urls_present": list(payload["meta"]["source_urls"].values()),
        "suspicious_encoding_markers": 0,
    }
    report["input_sha256_verified"] = True
    report["point_label_exact_match"] = True
    report["workbook_sha256"] = sha256(workbook_path)
    report["render_sha256"] = {name: sha256(ROOT / name) for name in report["render_files"]}
    metadata_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # Verify the round trip, including every Unicode string and recorded file hash.
    assert json.loads(metadata_path.read_text(encoding="utf-8")) == report
    print(json.dumps({"input_sha256_verified": True, "point_label_exact_match": True,
                      "workbook_sha256": report["workbook_sha256"],
                      "screenshots_hashed": len(report["render_sha256"])}))


if __name__ == "__main__":
    main()
