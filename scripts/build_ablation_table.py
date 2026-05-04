#!/usr/bin/env python3
"""Build Table-5 style ablation summary."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build ablation matrix table A1-A7.")
    parser.add_argument(
        "--status",
        type=Path,
        default=PROJECT_ROOT / "runs/ablation_matrix/status.json",
        help="Status file from run_ablation_matrix.py",
    )
    parser.add_argument(
        "--outdir",
        type=Path,
        default=PROJECT_ROOT / "runs/ablation_matrix/tables",
        help="Output directory for ablation tables.",
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


def _diag(run_root: Path) -> dict:
    payload = _read_json(run_root / "diagnostics_summary.json")
    if not isinstance(payload, dict):
        return {}
    rows = payload.get("rows", [])
    if not isinstance(rows, list) or not rows:
        return {}
    growth = [row.get("growth_ratio", 0.0) for row in rows if isinstance(row, dict)]
    locality = [row.get("patch_locality_ratio", 0.0) for row in rows if isinstance(row, dict)]
    return {
        "growth_ratio_max": max(growth) if growth else 0.0,
        "patch_locality_avg": (sum(locality) / len(locality)) if locality else 0.0,
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

    rows = []
    reference_f1 = None
    for item in status:
        if not isinstance(item, dict):
            continue
        if item.get("id") == "A0":
            run_root = Path(item.get("run_root", ""))
            if not run_root.is_absolute():
                run_root = PROJECT_ROOT / run_root
            reference_f1 = _metric_f1(run_root)
            break

    for item in status:
        if not isinstance(item, dict):
            continue
        run_root = Path(item.get("run_root", ""))
        if not run_root.is_absolute():
            run_root = PROJECT_ROOT / run_root
        f1 = _metric_f1(run_root)
        cq = _cq_rate(run_root)
        diag = _diag(run_root)
        delta = None
        if isinstance(reference_f1, (int, float)) and isinstance(f1, (int, float)):
            delta = f1 - float(reference_f1)
        rows.append(
            {
                "id": item.get("id"),
                "name": item.get("name"),
                "question": item.get("question"),
                "exit_code": item.get("exit_code"),
                "runtime_seconds": item.get("runtime_seconds"),
                "f1_semantic": f1,
                "delta_vs_A0": delta,
                "cq_pass_rate": cq,
                "growth_ratio_max": diag.get("growth_ratio_max"),
                "patch_locality_avg": diag.get("patch_locality_avg"),
                "run_root": str(run_root),
            }
        )

    headers = [
        "id",
        "name",
        "question",
        "exit_code",
        "runtime_seconds",
        "f1_semantic",
        "delta_vs_A0",
        "cq_pass_rate",
        "growth_ratio_max",
        "patch_locality_avg",
        "run_root",
    ]
    _write_csv(args.outdir / "ablation_matrix_table.csv", rows, headers)
    (args.outdir / "ablation_matrix_table.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(f"Wrote ablation table -> {args.outdir}")


if __name__ == "__main__":
    main()
