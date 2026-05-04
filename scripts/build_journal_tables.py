#!/usr/bin/env python3
"""Build journal-ready summary tables from run outputs."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build summary CSV tables for journal experiments")
    parser.add_argument(
        "--status",
        type=Path,
        default=PROJECT_ROOT / "runs/journal_execution_status.json",
        help="Execution status JSON from run_journal_layers.py",
    )
    parser.add_argument(
        "--outdir",
        type=Path,
        default=PROJECT_ROOT / "runs/journal_tables",
        help="Directory for CSV outputs.",
    )
    return parser.parse_args()


def _read_json(path: Path) -> dict | list | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _metric_f1(run_root: Path) -> float | None:
    metrics = _read_json(run_root / "final/metrics_semantic.json")
    if not isinstance(metrics, dict):
        metrics = _read_json(run_root / "metrics_semantic.json")
    if isinstance(metrics, dict):
        return metrics.get("f1")
    return None


def _cq_pass_rate(run_root: Path) -> float | None:
    cq = _read_json(run_root / "final/cq_results.json")
    if not isinstance(cq, dict):
        cq = _read_json(run_root / "cq_results.json")
    if isinstance(cq, dict):
        return cq.get("pass_rate")
    return None


def _error_taxonomy_counts(run_root: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    payload = _read_json(run_root / "diagnostics_summary.json")
    if not isinstance(payload, dict):
        return counts
    rows = payload.get("rows", [])
    if not isinstance(rows, list):
        return counts
    for row in rows:
        if not isinstance(row, dict):
            continue
        for code in row.get("error_taxonomy", []) or []:
            counts[code] = counts.get(code, 0) + 1
    return counts


def _resolve_run_root(exp_id: str) -> Path:
    if exp_id.startswith("E-DIAG-4-S"):
        seed = exp_id.split("S", 1)[1]
        return PROJECT_ROOT / "runs/journal/E-DIAG-4" / f"seed_{seed}"
    return PROJECT_ROOT / "runs/journal" / exp_id


def _write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in fieldnames})


def _token_total(run_root: Path) -> int | None:
    report = _read_json(run_root / "run_report.json")
    if not isinstance(report, dict):
        return None
    usage = report.get("token_usage")
    if not isinstance(usage, dict):
        return None
    total = usage.get("total_tokens")
    if isinstance(total, int):
        return total
    return None


def _seed_stats(seed_rows: list[dict]) -> dict:
    values = []
    for row in seed_rows:
        value = row.get("f1_semantic")
        if isinstance(value, (int, float)):
            values.append(float(value))
        elif isinstance(value, str) and value:
            try:
                values.append(float(value))
            except ValueError:
                pass
    if not values:
        return {"count": 0, "mean_f1": None, "std_f1": None}
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    return {"count": len(values), "mean_f1": mean, "std_f1": math.sqrt(variance)}


def main() -> None:
    args = parse_args()
    status = _read_json(args.status)
    if not isinstance(status, list):
        raise SystemExit(f"Missing or invalid status file: {args.status}")

    master_rows = []
    error_rows = []
    seed_rows = []

    for item in status:
        if not isinstance(item, dict):
            continue
        exp_id = str(item.get("id", ""))
        run_root = _resolve_run_root(exp_id)
        f1 = _metric_f1(run_root)
        cq_pass = _cq_pass_rate(run_root)
        token_total = _token_total(run_root)
        runtime = item.get("runtime_seconds")
        cost_proxy = None
        if isinstance(runtime, (int, float)) and isinstance(token_total, int):
            # Lightweight proxy for efficiency tradeoff reporting.
            cost_proxy = (token_total / 1000.0) * float(runtime)
        master_rows.append(
            {
                "id": exp_id,
                "phase_id": item.get("phase_id", exp_id),
                "layer": item.get("layer"),
                "exit_code": item.get("exit_code"),
                "runtime_seconds": item.get("runtime_seconds"),
                "f1_semantic": f1,
                "cq_pass_rate": cq_pass,
                "token_total": token_total,
                "cost_proxy": cost_proxy,
                "run_root": str(run_root),
            }
        )
        taxonomy_counts = _error_taxonomy_counts(run_root)
        for code, count in sorted(taxonomy_counts.items()):
            error_rows.append({"id": exp_id, "error_code": code, "count": count})
        if exp_id.startswith("E-DIAG-4-S"):
            seed_rows.append(
                {
                    "id": exp_id,
                    "seed": exp_id.split("S", 1)[1],
                    "f1_semantic": f1,
                    "cq_pass_rate": cq_pass,
                    "runtime_seconds": item.get("runtime_seconds"),
                    "token_total": token_total,
                }
            )

    seed_summary = _seed_stats(seed_rows)
    master_json = {
        "rows": master_rows,
        "seed_summary": seed_summary,
    }
    (args.outdir / "master_results.json").write_text(json.dumps(master_json, indent=2), encoding="utf-8")

    _write_csv(
        args.outdir / "master_results.csv",
        master_rows,
        [
            "id",
            "phase_id",
            "layer",
            "exit_code",
            "runtime_seconds",
            "f1_semantic",
            "cq_pass_rate",
            "token_total",
            "cost_proxy",
            "run_root",
        ],
    )
    _write_csv(args.outdir / "error_taxonomy_table.csv", error_rows, ["id", "error_code", "count"])
    _write_csv(
        args.outdir / "seed_variance_table.csv",
        seed_rows,
        ["id", "seed", "f1_semantic", "cq_pass_rate", "runtime_seconds", "token_total"],
    )
    _write_csv(
        args.outdir / "seed_variance_summary.csv",
        [seed_summary],
        ["count", "mean_f1", "std_f1"],
    )
    print(f"Wrote tables to {args.outdir}")


if __name__ == "__main__":
    main()
