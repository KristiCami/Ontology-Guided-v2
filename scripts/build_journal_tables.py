#!/usr/bin/env python3
"""Build journal-ready summary tables from run outputs."""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
from collections import defaultdict
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


_SEED_SUFFIX_PATTERN = re.compile(r"-S(\d+)$")


def _parse_seed_id(exp_id: str) -> tuple[str, str | None]:
    """Split ``<base>-S<seed>`` into ``(base, seed)``; returns seed=None when absent."""

    match = _SEED_SUFFIX_PATTERN.search(exp_id)
    if not match:
        return exp_id, None
    base = exp_id[: match.start()]
    return base, match.group(1)


def _resolve_run_root(exp_id: str) -> Path:
    base, seed = _parse_seed_id(exp_id)
    if seed is not None:
        return PROJECT_ROOT / "runs/journal" / base / f"seed_{seed}"
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
    """Aggregate F1 across one base experiment's seed runs (legacy E-DIAG-4 path)."""

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


def _aggregate_per_base(rows_by_base: dict[str, list[dict]]) -> list[dict]:
    """Mean/std of f1_semantic and cq_pass_rate per base experiment id."""

    summaries: list[dict] = []
    for base_id in sorted(rows_by_base.keys()):
        rows = rows_by_base[base_id]
        f1_values: list[float] = []
        cq_values: list[float] = []
        token_values: list[float] = []
        for row in rows:
            f1 = row.get("f1_semantic")
            if isinstance(f1, (int, float)):
                f1_values.append(float(f1))
            cq = row.get("cq_pass_rate")
            if isinstance(cq, (int, float)):
                cq_values.append(float(cq))
            tokens = row.get("token_total")
            if isinstance(tokens, (int, float)):
                token_values.append(float(tokens))

        def _stats(values: list[float]) -> tuple[float | None, float | None]:
            if not values:
                return None, None
            m = sum(values) / len(values)
            v = sum((x - m) ** 2 for x in values) / len(values)
            return m, math.sqrt(v)

        mean_f1, std_f1 = _stats(f1_values)
        mean_cq, std_cq = _stats(cq_values)
        mean_tokens, _ = _stats(token_values)
        summaries.append(
            {
                "base_id": base_id,
                "seed_count": len(rows),
                "mean_f1": mean_f1,
                "std_f1": std_f1,
                "mean_cq_pass_rate": mean_cq,
                "std_cq_pass_rate": std_cq,
                "mean_token_total": mean_tokens,
                "seeds": ",".join(sorted({str(r.get("seed")) for r in rows if r.get("seed") is not None})),
            }
        )
    return summaries


def main() -> None:
    args = parse_args()
    status = _read_json(args.status)
    if not isinstance(status, list):
        raise SystemExit(f"Missing or invalid status file: {args.status}")

    master_rows = []
    error_rows = []
    seed_rows = []
    rows_by_base: dict[str, list[dict]] = defaultdict(list)

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
        base_id, seed = _parse_seed_id(exp_id)
        phase_id = item.get("phase_id", base_id if seed is not None else exp_id)
        master_rows.append(
            {
                "id": exp_id,
                "phase_id": phase_id,
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
        if seed is not None:
            seed_row = {
                "id": exp_id,
                "base_id": base_id,
                "seed": seed,
                "f1_semantic": f1,
                "cq_pass_rate": cq_pass,
                "runtime_seconds": item.get("runtime_seconds"),
                "token_total": token_total,
            }
            seed_rows.append(seed_row)
            rows_by_base[base_id].append(seed_row)

    diag4_rows = [r for r in seed_rows if r.get("base_id") == "E-DIAG-4"]
    seed_summary = _seed_stats(diag4_rows)
    per_base_summaries = _aggregate_per_base(dict(rows_by_base))

    master_json = {
        "rows": master_rows,
        "seed_summary": seed_summary,
        "per_base_seed_summary": per_base_summaries,
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
        ["id", "base_id", "seed", "f1_semantic", "cq_pass_rate", "runtime_seconds", "token_total"],
    )
    _write_csv(
        args.outdir / "seed_variance_summary.csv",
        [seed_summary],
        ["count", "mean_f1", "std_f1"],
    )
    _write_csv(
        args.outdir / "novelty_seed_variance.csv",
        per_base_summaries,
        [
            "base_id",
            "seed_count",
            "seeds",
            "mean_f1",
            "std_f1",
            "mean_cq_pass_rate",
            "std_cq_pass_rate",
            "mean_token_total",
        ],
    )
    print(f"Wrote tables to {args.outdir}")


if __name__ == "__main__":
    main()
