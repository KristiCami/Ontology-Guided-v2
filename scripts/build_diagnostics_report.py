#!/usr/bin/env python3
"""Build diagnostics artifacts: plots, error tables, repair dynamics section."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from og_nsd.error_taxonomy import (  # noqa: E402
    CANONICAL_FAILURE_TAGS,
    FAILURE_TAXONOMY_META,
    taxonomy_meta_for_tag,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build diagnostics report from E4 run outputs.")
    parser.add_argument(
        "--input-root",
        type=Path,
        default=PROJECT_ROOT / "runs/journal/E-DIAG-1",
        help="Run directory containing diagnostics_summary.json",
    )
    parser.add_argument(
        "--outdir",
        type=Path,
        default=PROJECT_ROOT / "runs/diagnostics_report",
        help="Output directory for diagnostics artifacts.",
    )
    return parser.parse_args()


def _read_json(path: Path):
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _write_csv(path: Path, rows: list[dict], headers: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in headers})


def _build_rows(payload: dict) -> list[dict]:
    rows = payload.get("rows", [])
    if not isinstance(rows, list):
        return []
    normalized = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        normalized.append(
            {
                "iteration": row.get("iteration"),
                "cq_pass_rate": row.get("cq_pass_rate"),
                "hard_violations": row.get("hard_violations"),
                "soft_violations": row.get("soft_violations"),
                "growth_ratio": row.get("growth_ratio"),
                "new_triples": row.get("new_triples"),
                "changed_triples": row.get("changed_triples"),
                "patch_count": row.get("patch_count"),
                "patch_locality_ratio": row.get("patch_locality_ratio"),
                "new_classes_count": row.get("new_classes_count"),
                "new_properties_count": row.get("new_properties_count"),
                "no_gain_streak": row.get("no_gain_streak"),
                "stop_reason": row.get("stop_reason"),
                "error_taxonomy": "|".join(row.get("error_taxonomy", []) or []),
            }
        )
    return normalized


def _build_error_rows(rows: list[dict]) -> list[dict]:
    counts: dict[str, int] = {}
    for row in rows:
        tags = str(row.get("error_taxonomy", "")).split("|") if row.get("error_taxonomy") else []
        for tag in tags:
            if not tag:
                continue
            counts[tag] = counts.get(tag, 0) + 1
    return [{"error_code": key, "count": value} for key, value in sorted(counts.items())]


def _build_taxonomy_reference_rows() -> list[dict]:
    rows: list[dict] = []
    for code in sorted(FAILURE_TAXONOMY_META.keys(), key=lambda c: int(c[1:])):
        title, desc = FAILURE_TAXONOMY_META[code]
        rows.append(
            {
                "code": code,
                "title": title,
                "description": desc,
                "canonical_tag": CANONICAL_FAILURE_TAGS[code],
            }
        )
    return rows


def _write_markdown_section(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("# Repair dynamics\n\nNo diagnostics rows found.\n", encoding="utf-8")
        return
    peak_growth = max(float(row.get("growth_ratio") or 0.0) for row in rows)
    max_no_gain = max(int(row.get("no_gain_streak") or 0) for row in rows)
    final = rows[-1]
    content = (
        "# Repair dynamics\n\n"
        f"- Iterations observed: {len(rows)}\n"
        f"- Peak growth ratio: {peak_growth:.3f}\n"
        f"- Max no-gain streak: {max_no_gain}\n"
        f"- Final CQ pass rate: {float(final.get('cq_pass_rate') or 0.0):.3f}\n"
        f"- Final stop reason: `{final.get('stop_reason')}`\n\n"
        "This section is auto-generated from iteration diagnostics and can be used as seed text for the journal diagnostics subsection.\n"
    )
    path.write_text(content, encoding="utf-8")


def _plot(rows: list[dict], outdir: Path) -> None:
    try:
        import matplotlib.pyplot as plt  # type: ignore
    except Exception:
        (outdir / "plot_fallback.json").write_text(
            json.dumps({"note": "matplotlib not available", "rows": len(rows)}, indent=2),
            encoding="utf-8",
        )
        return

    iterations = [int(row.get("iteration") or 0) for row in rows]
    cq = [float(row.get("cq_pass_rate") or 0.0) for row in rows]
    hard = [float(row.get("hard_violations") or 0.0) for row in rows]
    soft = [float(row.get("soft_violations") or 0.0) for row in rows]
    growth = [float(row.get("growth_ratio") or 0.0) for row in rows]

    plt.figure(figsize=(8, 4))
    plt.plot(iterations, cq, marker="o", label="CQ pass rate")
    plt.plot(iterations, hard, marker="s", label="Hard violations")
    plt.plot(iterations, soft, marker="^", label="Soft violations")
    plt.xlabel("Iteration")
    plt.ylabel("Value")
    plt.title("Repair dynamics: CQ and SHACL")
    plt.legend()
    plt.tight_layout()
    plt.savefig(outdir / "repair_dynamics_cq_shacl.png", dpi=180)
    plt.close()

    plt.figure(figsize=(8, 4))
    plt.plot(iterations, growth, marker="o", color="tab:red")
    plt.xlabel("Iteration")
    plt.ylabel("Growth ratio")
    plt.title("Graph growth ratio across iterations")
    plt.tight_layout()
    plt.savefig(outdir / "repair_growth_ratio.png", dpi=180)
    plt.close()


def main() -> None:
    args = parse_args()
    args.outdir.mkdir(parents=True, exist_ok=True)
    payload = _read_json(args.input_root / "diagnostics_summary.json")
    if not isinstance(payload, dict):
        raise SystemExit(f"Missing diagnostics_summary.json under {args.input_root}")

    rows = _build_rows(payload)
    error_rows = _build_error_rows(rows)
    _write_csv(
        args.outdir / "diagnostics_iteration_table.csv",
        rows,
        [
            "iteration",
            "cq_pass_rate",
            "hard_violations",
            "soft_violations",
            "growth_ratio",
            "new_triples",
            "changed_triples",
            "patch_count",
            "patch_locality_ratio",
            "new_classes_count",
            "new_properties_count",
            "no_gain_streak",
            "stop_reason",
            "error_taxonomy",
        ],
    )
    _write_csv(args.outdir / "diagnostics_error_table.csv", error_rows, ["error_code", "count"])
    enriched_errors = []
    for row in error_rows:
        code, title, desc = taxonomy_meta_for_tag(str(row.get("error_code", "")))
        enriched_errors.append(
            {
                "error_code": row.get("error_code"),
                "count": row.get("count"),
                "taxonomy_code": code,
                "title": title,
                "description": desc,
            }
        )
    _write_csv(
        args.outdir / "diagnostics_error_table_with_descriptions.csv",
        enriched_errors,
        ["error_code", "count", "taxonomy_code", "title", "description"],
    )
    _write_csv(
        args.outdir / "failure_taxonomy_reference.csv",
        _build_taxonomy_reference_rows(),
        ["code", "title", "description", "canonical_tag"],
    )
    _write_markdown_section(args.outdir / "repair_dynamics_section.md", rows)
    _plot(rows, args.outdir)
    print(f"Wrote diagnostics report artifacts -> {args.outdir}")


if __name__ == "__main__":
    main()
