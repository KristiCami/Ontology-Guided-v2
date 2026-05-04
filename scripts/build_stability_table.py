#!/usr/bin/env python3
"""Build Table-4 style summary for SA variants."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build stability-aware variants summary table.")
    parser.add_argument(
        "--status",
        type=Path,
        default=PROJECT_ROOT / "runs/stability_core/status.json",
        help="Status file from run_stability_core.py",
    )
    parser.add_argument(
        "--outdir",
        type=Path,
        default=PROJECT_ROOT / "runs/stability_core/tables",
        help="Output directory for SA tables.",
    )
    return parser.parse_args()


def _read_json(path: Path):
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _metric_f1(run_root: Path) -> float | None:
    for path in [run_root / "final/metrics_semantic.json", run_root / "metrics_semantic.json"]:
        payload = _read_json(path)
        if isinstance(payload, dict):
            return payload.get("f1")
    return None


def _cq_rate(run_root: Path) -> float | None:
    for path in [run_root / "final/cq_results.json", run_root / "cq_results.json"]:
        payload = _read_json(path)
        if isinstance(payload, dict):
            return payload.get("pass_rate")
    return None


def _diagnostics(run_root: Path) -> dict:
    payload = _read_json(run_root / "diagnostics_summary.json")
    if not isinstance(payload, dict):
        return {}
    rows = payload.get("rows", [])
    if not isinstance(rows, list) or not rows:
        return {}
    last = rows[-1] if isinstance(rows[-1], dict) else {}
    growth_max = max((row.get("growth_ratio", 0.0) for row in rows if isinstance(row, dict)), default=0.0)
    no_gain_max = max((row.get("no_gain_streak", 0) for row in rows if isinstance(row, dict)), default=0)
    locality_avg_values = [row.get("patch_locality_ratio") for row in rows if isinstance(row, dict)]
    locality_avg_values = [v for v in locality_avg_values if isinstance(v, (int, float))]
    locality_avg = (sum(locality_avg_values) / len(locality_avg_values)) if locality_avg_values else 0.0
    error_events = 0
    for row in rows:
        if isinstance(row, dict):
            error_events += len(row.get("error_taxonomy", []) or [])
    return {
        "stability_variant": payload.get("stability_variant"),
        "feedback_variant": payload.get("feedback_variant"),
        "growth_ratio_max": growth_max,
        "no_gain_streak_max": no_gain_max,
        "patch_locality_avg": locality_avg,
        "error_taxonomy_events": error_events,
        "final_stop_reason": last.get("stop_reason"),
    }


def _write_csv(path: Path, rows: list[dict], headers: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in headers})


def main() -> None:
    args = parse_args()
    status = _read_json(args.status)
    if not isinstance(status, list):
        raise SystemExit(f"Missing status file: {args.status}")

    table_rows = []
    for item in status:
        if not isinstance(item, dict):
            continue
        run_root = Path(item.get("run_root", ""))
        if not run_root.is_absolute():
            run_root = PROJECT_ROOT / run_root
        diag = _diagnostics(run_root)
        table_rows.append(
            {
                "id": item.get("id"),
                "description": item.get("description"),
                "exit_code": item.get("exit_code"),
                "runtime_seconds": item.get("runtime_seconds"),
                "f1_semantic": _metric_f1(run_root),
                "cq_pass_rate": _cq_rate(run_root),
                "stability_variant": diag.get("stability_variant"),
                "feedback_variant": diag.get("feedback_variant"),
                "growth_ratio_max": diag.get("growth_ratio_max"),
                "no_gain_streak_max": diag.get("no_gain_streak_max"),
                "patch_locality_avg": diag.get("patch_locality_avg"),
                "error_taxonomy_events": diag.get("error_taxonomy_events"),
                "final_stop_reason": diag.get("final_stop_reason"),
                "run_root": str(run_root),
            }
        )

    headers = [
        "id",
        "description",
        "exit_code",
        "runtime_seconds",
        "f1_semantic",
        "cq_pass_rate",
        "stability_variant",
        "feedback_variant",
        "growth_ratio_max",
        "no_gain_streak_max",
        "patch_locality_avg",
        "error_taxonomy_events",
        "final_stop_reason",
        "run_root",
    ]
    _write_csv(args.outdir / "stability_variants_table.csv", table_rows, headers)
    (args.outdir / "stability_variants_table.json").write_text(
        json.dumps(table_rows, indent=2), encoding="utf-8"
    )
    print(f"Wrote stability table -> {args.outdir}")


if __name__ == "__main__":
    main()
