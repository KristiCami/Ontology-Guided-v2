#!/usr/bin/env python3
"""Normalize requirement JSON/JSONL into [{title,text}, ...] format.

Usage:
  python scripts/normalize_requirements_json.py \
    --input data/requirements/source.jsonl \
    --output data/requirements/normalized.jsonl
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _read_records(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []

    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return [parsed]
        if isinstance(parsed, list):
            return [item for item in parsed if isinstance(item, dict)]
        raise ValueError("Input JSON must be an object or array of objects.")
    except json.JSONDecodeError:
        records: list[dict[str, Any]] = []
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("//"):
                continue
            obj = json.loads(stripped)
            if isinstance(obj, dict):
                records.append(obj)
        return records


def _to_clean_records(records: list[dict[str, Any]]) -> list[dict[str, str]]:
    clean: list[dict[str, str]] = []
    for idx, rec in enumerate(records, start=1):
        raw_text = str(rec.get("text", "")).strip()
        if not raw_text:
            # Skip empty entries to keep output usable in runs.
            continue
        clean.append({"title": f"Requirement {idx}", "text": raw_text})
    return clean


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize requirements into title+text JSON array.")
    parser.add_argument("--input", type=Path, required=True, help="Source JSON/JSONL file")
    parser.add_argument("--output", type=Path, required=True, help="Destination normalized JSON file")
    args = parser.parse_args()

    records = _read_records(args.input)
    clean = _to_clean_records(records)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(clean, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Normalized {len(clean)} requirements -> {args.output}")


if __name__ == "__main__":
    main()
