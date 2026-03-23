#!/usr/bin/env python3
"""Extract and compare Ontology Hub cases from raw local sources.

This helper is optional and intended for maintainers that have access to the
non-public raw validation files used during the initial normalization process.
It is not required to execute the framework or the automated component tests.
"""

import csv
import json
import os
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[4]
VALIDATION_DIR = ROOT / "docs_" / "logs" / "validation"
TSV_PATH = Path(os.environ.get("ONTOLOGY_HUB_CASES_TSV", VALIDATION_DIR / "casos_prueba_extraidos.tsv"))
XLSX_PATH = Path(os.environ.get("ONTOLOGY_HUB_CASES_XLSX", VALIDATION_DIR / "A5.1_Casos_Prueba_v2.xlsx"))
XLSX_SHEET = "xl/worksheets/sheet4.xml"
XML_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def ensure_raw_sources_available():
    missing = [str(path) for path in (TSV_PATH, XLSX_PATH) if not path.exists()]
    if not missing:
        return

    print(
        "Raw Ontology Hub case sources are not available in this clone.\n"
        "This helper is optional and only works when the local raw TSV/XLSX files are present.\n"
        f"Missing: {', '.join(missing)}",
        file=sys.stderr,
    )
    raise SystemExit(2)


def load_tsv_rows():
    with TSV_PATH.open("r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        return [row for row in reader if row.get("Componente") == "Ontology Hub"]


def load_xlsx_rows():
    with zipfile.ZipFile(XLSX_PATH) as archive:
        shared_strings = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            for item in root.findall(f"{XML_NS}si"):
                text_parts = [node.text or "" for node in item.iter(f"{XML_NS}t")]
                shared_strings.append("".join(text_parts))

        sheet_root = ET.fromstring(archive.read(XLSX_SHEET))
        rows = []
        headers = None
        for row in sheet_root.findall(f".//{XML_NS}row"):
            values = []
            for cell in row.findall(f"{XML_NS}c"):
                value_node = cell.find(f"{XML_NS}v")
                value = ""
                if value_node is not None:
                    value = value_node.text or ""
                    if cell.attrib.get("t") == "s":
                        value = shared_strings[int(value)]
                values.append(value)

            if headers is None:
                headers = values
                continue

            item = dict(zip(headers, values))
            if item.get("Componente") == "Ontology Hub":
                rows.append(item)
        return rows


def normalize(rows):
    normalized = []
    for row in rows:
        normalized.append(
            {
                "id": row["ID Prueba"],
                "component": "ontology_hub",
                "context": row["Contexto de validación"],
                "dimension": row["Dimensión de validación en Espacio de Datos"],
                "description": row["Funcionalidad a validar"],
                "procedure": row["Procedimiento"],
                "expected_result": row["Criterio de aceptación"],
                "traceability": [token.strip() for token in row["Trazabilidad funcional"].split(",") if token.strip()],
            }
        )
    return normalized


def main():
    ensure_raw_sources_available()

    tsv_rows = load_tsv_rows()
    xlsx_rows = load_xlsx_rows()

    tsv_normalized = normalize(tsv_rows)
    xlsx_normalized = normalize(xlsx_rows)

    if tsv_normalized != xlsx_normalized:
        print("TSV and XLSX sources do not match for Ontology Hub cases.", file=sys.stderr)
        print(json.dumps({"tsv": tsv_normalized, "xlsx": xlsx_normalized}, indent=2, ensure_ascii=False))
        raise SystemExit(1)

    print(json.dumps(tsv_normalized, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
